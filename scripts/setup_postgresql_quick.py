"""
Quick setup script after PostgreSQL installation.
Creates the database and tests connection.
"""
import sys
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger


def database_exists():
    """Check if the binance_bot database already exists."""
    try:
        # Use psql to query pg_database system catalog
        result = subprocess.run(
            ["psql", "-U", "postgres", "-tAc", "SELECT 1 FROM pg_database WHERE datname='binance_bot';"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip() == "1":
            return True
        return False
    except Exception:
        # If check fails, we'll try to create and handle the error
        return None


def create_database():
    """Create the binance_bot database if it doesn't exist."""
    logger.info("Checking if database 'binance_bot' exists...")
    
    # First, check if database already exists
    exists = database_exists()
    if exists is True:
        logger.info("✓ Database 'binance_bot' already exists - skipping creation")
        return True
    elif exists is False:
        logger.info("Database 'binance_bot' does not exist. Creating...")
    else:
        logger.info("Could not verify database existence. Attempting to create...")
    
    try:
        # Try to create database
        result = subprocess.run(
            ["createdb", "-U", "postgres", "binance_bot"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            logger.info("✓ Database 'binance_bot' created successfully")
            return True
        elif "already exists" in result.stderr.lower():
            logger.info("✓ Database 'binance_bot' already exists (detected during creation)")
            return True
        else:
            logger.warning(f"⚠ Error creating database: {result.stderr}")
            logger.info("")
            logger.info("You can create it manually:")
            logger.info("  psql -U postgres")
            logger.info("  CREATE DATABASE binance_bot;")
            logger.info("  \\q")
            return False
            
    except FileNotFoundError:
        logger.warning("⚠ 'createdb' command not found")
        logger.info("Make sure PostgreSQL bin directory is in your PATH")
        logger.info("")
        logger.info("You can create the database manually:")
        logger.info("  psql -U postgres")
        logger.info("  CREATE DATABASE binance_bot;")
        logger.info("  \\q")
        return False
    except Exception as e:
        logger.error(f"✗ Error: {e}")
        return False


def test_connection():
    """Test database connection."""
    logger.info("")
    logger.info("Testing database connection...")
    logger.info("")
    
    try:
        from app.core.database import init_database, get_engine, close_database
        from sqlalchemy import text
        
        init_database()
        engine = get_engine()
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            logger.info(f"✓ Connected successfully!")
            logger.info(f"  PostgreSQL: {version.split(',')[0]}")
            
            result = conn.execute(text("SELECT current_database()"))
            db_name = result.fetchone()[0]
            logger.info(f"  Database: {db_name}")
        
        close_database()
        return True
        
    except Exception as e:
        logger.error(f"✗ Connection failed: {e}")
        logger.info("")
        logger.info("Make sure:")
        logger.info("  1. PostgreSQL service is running")
        logger.info("  2. Your .env file has correct DATABASE_URL")
        logger.info("  3. Database 'binance_bot' exists")
        return False


def main():
    """Run setup steps."""
    logger.info("=" * 60)
    logger.info("PostgreSQL Quick Setup")
    logger.info("=" * 60)
    logger.info("")
    
    # Step 1: Create database
    db_created = create_database()
    logger.info("")
    
    # Step 2: Test connection
    if db_created:
        connection_ok = test_connection()
        
        if connection_ok:
            logger.info("")
            logger.info("=" * 60)
            logger.info("✓ Setup Complete!")
            logger.info("=" * 60)
            logger.info("")
            logger.info("Next steps:")
            logger.info("  1. Generate migration: python -m alembic revision --autogenerate -m \"Initial schema\"")
            logger.info("  2. Apply migration: python -m alembic upgrade head")
            logger.info("  3. Run tests: python scripts/test_database_setup.py")
            return 0
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("Setup Incomplete")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Please check the errors above and try again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

