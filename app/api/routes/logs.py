"""API routes for log viewing and filtering."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/logs", tags=["logs"])


class LogEntry(BaseModel):
    """Represents a single log entry."""
    timestamp: str = Field(..., description="Log entry timestamp")
    level: str = Field(..., description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    module: str = Field(..., description="Module path")
    function: str = Field(..., description="Function name")
    line: int = Field(..., description="Line number")
    message: str = Field(..., description="Log message")
    raw_line: str = Field(..., description="Original log line")


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
    filtered = entries
    
    # Filter by symbol (case-insensitive search in message)
    if symbol:
        symbol_upper = symbol.upper()
        filtered = [e for e in filtered if symbol_upper in e.message.upper()]
    
    # Filter by log level
    if level:
        level_upper = level.upper()
        filtered = [e for e in filtered if e.level.upper() == level_upper]
    
    # Filter by date range
    if date_from:
        try:
            from_date = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            filtered = [
                e for e in filtered
                if datetime.strptime(e.timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) >= from_date
            ]
        except ValueError:
            pass  # Invalid date format, skip date filter
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            # Add 1 day to include the entire end date
            to_date = to_date.replace(hour=23, minute=59, second=59)
            filtered = [
                e for e in filtered
                if datetime.strptime(e.timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) <= to_date
            ]
        except ValueError:
            pass  # Invalid date format, skip date filter
    
    # Filter by search text (case-insensitive search in message, module, or function)
    if search_text:
        search_lower = search_text.lower()
        filtered = [
            e for e in filtered
            if search_lower in e.message.lower()
            or search_lower in e.module.lower()
            or search_lower in e.function.lower()
        ]
    
    # Filter by module
    if module:
        module_lower = module.lower()
        filtered = [e for e in filtered if module_lower in e.module.lower()]
    
    # Filter by function
    if function:
        function_lower = function.lower()
        filtered = [e for e in filtered if function_lower in e.function.lower()]
    
    return filtered


@router.get("/", response_model=LogResponse)
def get_logs(
    symbol: Optional[str] = Query(None, description="Filter by cryptocurrency symbol (e.g., BTCUSDT)"),
    level: Optional[str] = Query(None, description="Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"),
    date_from: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
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
    
    # Read all log entries
    all_entries = []
    for log_file in log_files:
        try:
            # Skip compressed files for now (would need zipfile support)
            if log_file.endswith(".zip"):
                continue
            
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    entry = parse_log_line(line)
                    if entry:
                        all_entries.append(entry)
        except Exception:
            # Skip files that can't be read
            continue
    
    total_count = len(all_entries)
    
    # Apply filters
    filtered_entries = filter_logs(
        all_entries,
        symbol=symbol,
        level=level,
        date_from=date_from,
        date_to=date_to,
        search_text=search_text,
        module=module,
        function=function,
    )
    
    # Sort by timestamp
    filtered_entries.sort(
        key=lambda e: datetime.strptime(e.timestamp, "%Y-%m-%d %H:%M:%S"),
        reverse=reverse
    )
    
    # Apply limit
    filtered_entries = filtered_entries[:limit]
    
    return LogResponse(
        entries=filtered_entries,
        total_count=total_count,
        filtered_count=len(filtered_entries)
    )


@router.get("/symbols", response_model=list[str])
def get_available_symbols() -> list[str]:
    """Get list of unique cryptocurrency symbols found in logs."""
    log_files = read_log_files()
    symbols = set()
    
    for log_file in log_files:
        if log_file.endswith(".zip"):
            continue
        
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    entry = parse_log_line(line)
                    if entry:
                        # Extract symbols from log messages (look for patterns like "BTCUSDT", "ETHUSDT", etc.)
                        # Pattern: uppercase letters/digits followed by USDT, BTC, ETH, etc.
                        symbol_pattern = r'\b([A-Z0-9]+(?:USDT|BTC|ETH|BNB|BUSD))\b'
                        matches = re.findall(symbol_pattern, entry.message.upper())
                        symbols.update(matches)
        except Exception:
            continue
    
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
    
    all_entries = []
    for log_file in log_files:
        if log_file.endswith(".zip"):
            continue
        
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    entry = parse_log_line(line)
                    if entry:
                        all_entries.append(entry)
                        stats["levels"][entry.level] = stats["levels"].get(entry.level, 0) + 1
                        stats["modules"][entry.module] = stats["modules"].get(entry.module, 0) + 1
        except Exception:
            continue
    
    if all_entries:
        timestamps = [datetime.strptime(e.timestamp, "%Y-%m-%d %H:%M:%S") for e in all_entries]
        stats["first_entry"] = min(timestamps).isoformat()
        stats["last_entry"] = max(timestamps).isoformat()
        stats["total_entries"] = len(all_entries)
    
    return stats

