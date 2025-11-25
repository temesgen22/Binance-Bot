import sys
from pathlib import Path
from loguru import logger


def configure_logging() -> None:
    """Configure logging to both console and file."""
    logger.remove()
    
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Log file path with rotation
    log_file = logs_dir / "bot.log"
    
    # Console output - use sys.stderr for better compatibility
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

