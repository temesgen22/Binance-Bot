"""API routes for log viewing and filtering."""
from __future__ import annotations

import heapq
import os
import re
from collections import deque
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from threading import Lock
from typing import Callable, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, PrivateAttr

router = APIRouter(prefix="/logs", tags=["logs"])

try:
    _cache_line_limit = int(os.getenv("LOG_VIEWER_CACHE_MAX_LINES", "50000"))
except ValueError:
    _cache_line_limit = 50000
MAX_CACHE_ENTRIES_PER_FILE = _cache_line_limit if _cache_line_limit > 0 else None

LOG_CACHE: dict[str, dict[str, object]] = {}
LOG_CACHE_LOCK = Lock()


class LogEntry(BaseModel):
    """Represents a single log entry."""
    timestamp: str = Field(..., description="Log entry timestamp")
    level: str = Field(..., description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    module: str = Field(..., description="Module path")
    function: str = Field(..., description="Function name")
    line: int = Field(..., description="Line number")
    message: str = Field(..., description="Log message")
    raw_line: str = Field(..., description="Original log line")

    _timestamp_cache: datetime | None = PrivateAttr(default=None)

    def get_timestamp(self) -> datetime:
        """Return the parsed timestamp, caching the conversion."""
        if self._timestamp_cache is None:
            self._timestamp_cache = datetime.strptime(self.timestamp, "%Y-%m-%d %H:%M:%S")
        return self._timestamp_cache


class LogResponse(BaseModel):
    """Response model for log queries."""
    entries: list[LogEntry] = Field(..., description="Filtered log entries")
    total_count: int = Field(..., description="Total number of entries found")
    filtered_count: int = Field(..., description="Number of entries after filtering")


def parse_log_line(line: str) -> Optional[LogEntry]:
    """Parse a single log line into a LogEntry object.
    
    Expected format: {time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} | {message}
    Example: 2025-11-24 01:18:35 | INFO     | app.services.strategy_runner:_load_from_redis:299 | Redis not enabled
    """
    # Pattern to match log format: timestamp | level | module:function:line | message
    pattern = r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\w+)\s+\| ([^:]+):([^:]+):(\d+) \| (.+)$"
    match = re.match(pattern, line.strip())
    
    if not match:
        return None
    
    timestamp, level, module, function, line_num, message = match.groups()
    
    return LogEntry(
        timestamp=timestamp,
        level=level.strip(),
        module=module.strip(),
        function=function.strip(),
        line=int(line_num),
        message=message.strip(),
        raw_line=line.strip()
    )


def read_log_files() -> list[str]:
    """Read all log files including rotated/compressed ones.
    
    Returns a list of log file paths to read.
    """
    logs_dir = Path("logs")
    if not logs_dir.exists():
        return []
    
    log_files = []
    
    # Main log file
    main_log = logs_dir / "bot.log"
    if main_log.exists():
        log_files.append(str(main_log))
    
    # Rotated log files (bot.log.1, bot.log.2, etc.)
    for i in range(1, 10):  # Check up to 9 rotated files
        rotated = logs_dir / f"bot.log.{i}"
        if rotated.exists():
            log_files.append(str(rotated))
    
    # Compressed log files (bot.log.YYYY-MM-DD.zip)
    for zip_file in logs_dir.glob("bot.log.*.zip"):
        log_files.append(str(zip_file))
    
    return log_files


def filter_logs(
    entries: list[LogEntry],
    symbol: Optional[str] = None,
    level: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search_text: Optional[str] = None,
    module: Optional[str] = None,
    function: Optional[str] = None,
) -> list[LogEntry]:
    """Filter log entries based on various criteria."""
    predicate = _make_filter_fn(
        symbol=symbol,
        level=level,
        date_from=date_from,
        date_to=date_to,
        search_text=search_text,
        module=module,
        function=function,
    )
    return [entry for entry in entries if predicate(entry)]


@router.get("/", response_model=LogResponse)
def get_logs(
    symbol: Optional[str] = Query(None, description="Filter by cryptocurrency symbol (e.g., BTCUSDT)"),
    level: Optional[str] = Query(None, description="Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"),
    date_from: Optional[str] = Query(None, description="Filter from date/time (YYYY-MM-DD or ISO datetime)"),
    date_to: Optional[str] = Query(None, description="Filter to date/time (YYYY-MM-DD or ISO datetime)"),
    search_text: Optional[str] = Query(None, description="Search text in message, module, or function"),
    module: Optional[str] = Query(None, description="Filter by module name"),
    function: Optional[str] = Query(None, description="Filter by function name"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of entries to return"),
    reverse: bool = Query(True, description="Return entries in reverse chronological order (newest first)"),
) -> LogResponse:
    """Get log entries with optional filtering.
    
    Supports filtering by:
    - Symbol: Cryptocurrency symbol (e.g., BTCUSDT, ETHUSDT)
    - Level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - Date range: From and to dates
    - Search text: Text search in messages, modules, or functions
    - Module: Filter by module path
    - Function: Filter by function name
    """
    log_files = read_log_files()

    if not log_files:
        return LogResponse(entries=[], total_count=0, filtered_count=0)

    predicate = _make_filter_fn(
        symbol=symbol,
        level=level,
        date_from=date_from,
        date_to=date_to,
        search_text=search_text,
        module=module,
        function=function,
    )

    total_count = 0
    filtered_count = 0
    heap: list[tuple[datetime, int, LogEntry]] = []
    forward_matches: list[LogEntry] = [] if not reverse else None
    entry_sequence = count()

    for log_file in log_files:
        if log_file.endswith(".zip"):
            continue

        entries, entry_count = _get_log_file_entries(log_file)
        total_count += entry_count

        for entry in entries:
            if not predicate(entry):
                continue

            filtered_count += 1

            if reverse:
                ts = entry.get_timestamp()
                heap_item = (ts, next(entry_sequence), entry)

                if len(heap) < limit:
                    heapq.heappush(heap, heap_item)
                else:
                    if ts > heap[0][0]:
                        heapq.heapreplace(heap, heap_item)
            else:
                forward_matches.append(entry)

    if reverse:
        limited_entries = [item[2] for item in sorted(heap, key=lambda pair: pair[0], reverse=True)]
    else:
        forward_matches.sort(key=lambda e: e.get_timestamp())
        limited_entries = forward_matches[:limit]

    return LogResponse(
        entries=limited_entries,
        total_count=total_count,
        filtered_count=filtered_count
    )


@router.get("/symbols", response_model=list[str])
def get_available_symbols() -> list[str]:
    """Get list of unique cryptocurrency symbols found in logs."""
    log_files = read_log_files()
    symbols = set()

    for log_file in log_files:
        if log_file.endswith(".zip"):
            continue

        entries, _ = _get_log_file_entries(log_file)

        for entry in entries:
            symbol_pattern = r'\b([A-Z0-9]+(?:USDT|BTC|ETH|BNB|BUSD))\b'
            matches = re.findall(symbol_pattern, entry.message.upper())
            symbols.update(matches)

    return sorted(list(symbols))


@router.get("/stats")
def get_log_stats() -> dict:
    """Get statistics about the logs."""
    log_files = read_log_files()

    stats = {
        "total_files": len([f for f in log_files if not f.endswith(".zip")]),
        "total_compressed": len([f for f in log_files if f.endswith(".zip")]),
        "levels": {},
        "modules": {},
        "first_entry": None,
        "last_entry": None,
    }

    timestamps: list[datetime] = []

    for log_file in log_files:
        if log_file.endswith(".zip"):
            continue

        entries, _ = _get_log_file_entries(log_file)

        for entry in entries:
            ts = entry.get_timestamp()
            timestamps.append(ts)
            stats["levels"][entry.level] = stats["levels"].get(entry.level, 0) + 1
            stats["modules"][entry.module] = stats["modules"].get(entry.module, 0) + 1

    if timestamps:
        stats["first_entry"] = min(timestamps).isoformat()
        stats["last_entry"] = max(timestamps).isoformat()
        stats["total_entries"] = len(timestamps)

    return stats


def _make_filter_fn(
    *,
    symbol: Optional[str],
    level: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    search_text: Optional[str],
    module: Optional[str],
    function: Optional[str],
) -> Callable[[LogEntry], bool]:
    """Build a predicate function matching all provided filters."""
    symbol_upper = symbol.upper() if symbol else None
    level_upper = level.upper() if level else None
    search_lower = search_text.lower() if search_text else None
    module_lower = module.lower() if module else None
    function_lower = function.lower() if function else None

    from_date = None
    if date_from:
        try:
            # Try ISO datetime format first (with time)
            if 'T' in date_from or '+' in date_from or date_from.count(':') >= 2:
                # ISO format: 2025-11-28T10:30:00 or 2025-11-28T10:30:00Z
                from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                if from_date.tzinfo is None:
                    from_date = from_date.replace(tzinfo=timezone.utc)
            else:
                # Date-only format: YYYY-MM-DD
                from_date = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            from_date = None

    to_date = None
    if date_to:
        try:
            # Try ISO datetime format first (with time)
            if 'T' in date_to or '+' in date_to or date_to.count(':') >= 2:
                # ISO format: 2025-11-28T10:30:00 or 2025-11-28T10:30:00Z
                to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                if to_date.tzinfo is None:
                    to_date = to_date.replace(tzinfo=timezone.utc)
            else:
                # Date-only format: YYYY-MM-DD (set to end of day)
                to_date = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                to_date = to_date.replace(hour=23, minute=59, second=59)
        except (ValueError, AttributeError):
            to_date = None

    def predicate(entry: LogEntry) -> bool:
        if symbol_upper:
            if symbol_upper not in entry.message.upper():
                return False

        if level_upper and entry.level.upper() != level_upper:
            return False

        if from_date or to_date:
            entry_ts = entry.get_timestamp().replace(tzinfo=timezone.utc)
            if from_date and entry_ts < from_date:
                return False
            if to_date and entry_ts > to_date:
                return False

        if search_lower:
            entry_message = entry.message.lower()
            if (
                search_lower not in entry_message
                and search_lower not in entry.module.lower()
                and search_lower not in entry.function.lower()
            ):
                return False

        if module_lower and module_lower not in entry.module.lower():
            return False

        if function_lower and function_lower not in entry.function.lower():
            return False

        return True

    return predicate


def _get_log_file_entries(log_file: str) -> tuple[list[LogEntry], int]:
    """Return cached entries and total line count for a log file."""
    path = Path(log_file)

    if os.getenv("PYTEST_CURRENT_TEST"):
        # During pytest runs, bypass caching to avoid interference with mocked files.
        return _read_file_uncached(log_file)

    try:
        stat = path.stat()
    except (FileNotFoundError, OSError):
        return _read_file_uncached(log_file)

    cache_key = str(path.resolve())

    with LOG_CACHE_LOCK:
        cached = LOG_CACHE.get(cache_key)

    if cached and cached["mtime"] == stat.st_mtime and cached["size"] == stat.st_size:
        return cached["entries"], cached["line_count"]  # type: ignore[return-value]

    entries: list[LogEntry]
    line_count: int

    if (
        cached
        and isinstance(cached.get("size"), (int, float))
        and stat.st_size > cached["size"]
        and stat.st_mtime >= cached["mtime"]  # type: ignore[index]
    ):
        entries, line_count = _read_incremental(path, cached)  # type: ignore[arg-type]
    else:
        entries, line_count = _read_full_file(path)

    cache_payload = {
        "mtime": stat.st_mtime,
        "size": stat.st_size,
        "entries": entries,
        "line_count": line_count,
    }

    with LOG_CACHE_LOCK:
        LOG_CACHE[cache_key] = cache_payload

    return entries, line_count


def _read_full_file(path: Path) -> tuple[list[LogEntry], int]:
    """Read entire log file into memory (bounded by cache max)."""
    entries_deque = deque(maxlen=MAX_CACHE_ENTRIES_PER_FILE)
    line_count = 0

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                entry = parse_log_line(line)
                if not entry:
                    continue
                line_count += 1
                entries_deque.append(entry)
    except (FileNotFoundError, OSError):
        return [], 0

    return list(entries_deque), line_count


def _read_incremental(path: Path, cached: dict[str, object]) -> tuple[list[LogEntry], int]:
    """Read only the newly appended portion of a log file."""
    previous_entries = cached.get("entries", [])
    entries_deque = deque(previous_entries, maxlen=MAX_CACHE_ENTRIES_PER_FILE)
    line_count = int(cached.get("line_count", len(entries_deque)))
    start_offset = int(cached.get("size", 0))

    new_entries = _read_new_entries_from_offset(path, start_offset)

    for entry in new_entries:
        line_count += 1
        entries_deque.append(entry)

    return list(entries_deque), line_count


def _read_new_entries_from_offset(path: Path, start_offset: int) -> list[LogEntry]:
    """Read and parse new log lines from a specific byte offset."""
    try:
        with path.open("rb") as f:
            f.seek(start_offset)
            data = f.read()
    except (FileNotFoundError, OSError):
        return []

    text = data.decode("utf-8", errors="ignore")
    entries = []
    for line in text.splitlines():
        entry = parse_log_line(line)
        if entry:
            entries.append(entry)
    return entries


def _read_file_uncached(log_file: str) -> tuple[list[LogEntry], int]:
    """Fallback reader used when stat information isn't available (e.g., during tests)."""
    entries_deque = deque(maxlen=MAX_CACHE_ENTRIES_PER_FILE)
    line_count = 0

    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                entry = parse_log_line(line)
                if not entry:
                    continue
                line_count += 1
                entries_deque.append(entry)
    except Exception:
        return [], 0

    return list(entries_deque), line_count

