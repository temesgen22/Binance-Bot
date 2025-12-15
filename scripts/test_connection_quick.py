"""
Quick database connection test.
Make sure your .env file has DATABASE_URL configured.
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
    logger.info("Database Connection Test")
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
        
        logger.info(f"Connecting to: postgresql://***@{display_url}")
        logger.info("")
        
        # Initialize database
        logger.info("Initializing connection...")
        init_database()
        logger.info("✓ Connection pool initialized")
        
        # Test connection
        engine = get_engine()
        logger.info("Testing connection...")
        
        with engine.connect() as conn:
            # Test version
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            logger.info(f"✓ Connected to PostgreSQL!")
            logger.info(f"  Version: {version.split(',')[0]}")
            
            # Test database
            result = conn.execute(text("SELECT current_database()"))
            db_name = result.fetchone()[0]
            logger.info(f"  Database: {db_name}")
            
            # Test if tables exist
            result = conn.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            table_count = result.fetchone()[0]
            logger.info(f"  Tables: {table_count}")
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("✓ Connection test PASSED!")
        logger.info("=" * 60)
        logger.info("")
        
        if table_count == 0:
            logger.info("Next steps:")
            logger.info("  1. Generate migration:")
            logger.info("     python -m alembic revision --autogenerate -m \"Initial schema\"")
            logger.info("")
            logger.info("  2. Apply migration:")
            logger.info("     python -m alembic upgrade head")
            logger.info("")
            logger.info("  3. Run full tests:")
            logger.info("     python scripts/test_database_setup.py")
        else:
            logger.info("Database is ready! Tables already exist.")
            logger.info("Run full tests: python scripts/test_database_setup.py")
        
        close_database()
        return 0
        
    except Exception as e:
        logger.error("")
        logger.error("✗ Connection test FAILED!")
        logger.error("")
        logger.error(f"Error: {type(e).__name__}: {e}")
        logger.error("")
        logger.error("Troubleshooting:")
        logger.error("  1. Check your .env file has DATABASE_URL")
        logger.error("  2. Format: DATABASE_URL=postgresql://postgres:PASSWORD@localhost:5432/binance_bot")
        logger.error("  3. Make sure PostgreSQL service is running")
        logger.error("  4. Verify database 'binance_bot' exists")
        logger.error("")
        
        import traceback
        traceback.print_exc()
        
        close_database()
        return 1


if __name__ == "__main__":
    sys.exit(main())


