import sys
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from loguru import logger


def serialize_record(record: Dict[str, Any]) -> str:
    """Serialize log record to JSON format.
    
    Includes correlation ID if available from contextvars.
    """
    try:
        from app.core.correlation_id import get_correlation_id
        correlation_id = get_correlation_id()
    except (ImportError, AttributeError, LookupError):
        correlation_id = None
    
    log_data = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "module": record["name"],
        "function": record["function"],
        "line": record["line"],
    }
    
    # Add correlation ID if available
    if correlation_id:
        log_data["correlation_id"] = correlation_id
    
    # Add exception info if present
    if "exception" in record:
        log_data["exception"] = {
            "type": record["exception"].type.__name__ if record["exception"].type else None,
            "value": str(record["exception"].value) if record["exception"].value else None,
        }
    
    # Add extra fields from record
    if "extra" in record:
        for key, value in record["extra"].items():
            if key not in ["correlation_id"]:  # Don't duplicate
                try:
                    # Only include JSON-serializable values
                    json.dumps(value)
                    log_data[key] = value
                except (TypeError, ValueError):
                    log_data[key] = str(value)
    
    return json.dumps(log_data, default=str)


def configure_logging(use_json: Optional[bool] = None) -> None:
    """Configure logging to both console and file.
    
    Args:
        use_json: If True, use JSON format for file logs. If None, reads from
                  LOG_JSON_FORMAT environment variable (default: False)
    """
    logger.remove()
    
    # Check if JSON format is enabled
    if use_json is None:
        use_json = os.getenv("LOG_JSON_FORMAT", "false").lower() in ("true", "1", "yes")
    
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Log file path with rotation
    log_file = logs_dir / "bot.log"
    
    # Console output - always use human-readable format
    logger.add(
        sink=sys.stderr,
        level="INFO",
        backtrace=False,
        diagnose=False,
        colorize=True,
        enqueue=False,  # Disable queue for immediate output
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | <level>{message}</level>",
    )
    
    # File output with rotation (10 MB per file, keep 5 files)
    if use_json:
        # JSON format for log aggregation systems (ELK, Splunk, etc.)
        logger.add(
            sink=str(log_file),
            level="DEBUG",  # More detailed logs in file
            rotation="10 MB",
            retention="5 days",  # Keep logs for 5 days
            compression="zip",  # Compress old logs
            backtrace=True,
            diagnose=True,
            enqueue=False,  # Disable queue for immediate write
            format=serialize_record,
            serialize=True,  # Enable serialization
        )
    else:
        # Human-readable format (default)
        logger.add(
            sink=str(log_file),
            level="DEBUG",  # More detailed logs in file
            rotation="10 MB",
            retention="5 days",  # Keep logs for 5 days
            compression="zip",  # Compress old logs
            backtrace=True,
            diagnose=True,
            enqueue=False,  # Disable queue for immediate write
            format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} | {message}",
        )

