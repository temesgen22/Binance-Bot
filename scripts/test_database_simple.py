"""
Simple database connection test.
Run this first to verify your database is accessible.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import get_settings
from app.core.database import init_database, get_engine, close_database
from loguru import logger
from sqlalchemy import text


def main():
    """Test database connection."""
    logger.info("=" * 60)
    logger.info("Simple Database Connection Test")
    logger.info("=" * 60)
    logger.info("")
    
    try:
        # Get settings
        settings = get_settings()
        db_url = settings.database_url
        
        # Mask password in URL for display
        if "@" in db_url:
            display_url = db_url.split("@")[-1]
        else:
            display_url = "***"
        
        logger.info(f"Database URL: postgresql://***@{display_url}")
        logger.info("")
        
        # Initialize database
        logger.info("Attempting to connect to database...")
        init_database()
        logger.info("✓ Database connection pool initialized")
        
        # Test connection
        engine = get_engine()
        logger.info("Testing connection...")
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            logger.info(f"✓ Connected successfully!")
            logger.info(f"  PostgreSQL version: {version.split(',')[0]}")
            
            # Test database exists
            result = conn.execute(text("SELECT current_database()"))
            db_name = result.fetchone()[0]
            logger.info(f"  Current database: {db_name}")
        
        logger.info("")
        logger.info("✓ Database connection test PASSED!")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Run: python -m alembic revision --autogenerate -m \"Initial schema\"")
        logger.info("  2. Run: python -m alembic upgrade head")
        logger.info("  3. Run: python scripts/test_database_setup.py")
        
        close_database()
        return 0
        
    except Exception as e:
        logger.error("")
        logger.error("✗ Database connection test FAILED!")
        logger.error("")
        logger.error(f"Error: {type(e).__name__}: {e}")
        logger.error("")
        logger.error("Troubleshooting:")
        logger.error("  1. Make sure PostgreSQL is running")
        logger.error("  2. Check your DATABASE_URL in .env file")
        logger.error("  3. Verify database exists: createdb binance_bot")
        logger.error("  4. Check credentials are correct")
        logger.error("")
        logger.error("Example DATABASE_URL:")
        logger.error("  DATABASE_URL=postgresql://postgres:postgres@localhost:5432/binance_bot")
        
        import traceback
        traceback.print_exc()
        
        close_database()
        return 1


if __name__ == "__main__":
    sys.exit(main())

