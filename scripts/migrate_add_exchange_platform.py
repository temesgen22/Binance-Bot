"""
Migration script to add exchange_platform column to accounts table.
Run this script to update the database schema.
"""
from sqlalchemy import text
from app.core.database import get_db_session, init_database
from loguru import logger


def migrate_add_exchange_platform():
    """Add exchange_platform column to accounts table."""
    # Initialize database connection
    init_database()
    
    with get_db_session() as db:
        try:
            # Check if column already exists
            result = db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='accounts' AND column_name='exchange_platform'
            """))
            
            if result.fetchone():
                logger.info("Column 'exchange_platform' already exists, skipping migration")
                return
            
            # Add exchange_platform column with default value
            db.execute(text("""
                ALTER TABLE accounts 
                ADD COLUMN exchange_platform VARCHAR(50) NOT NULL DEFAULT 'binance'
            """))
            
            # Create index for better query performance
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_accounts_exchange_platform 
                ON accounts(exchange_platform)
            """))
            
            db.commit()
            logger.info("✅ Successfully added exchange_platform column to accounts table")
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Error adding exchange_platform column: {e}")
            raise


if __name__ == "__main__":
    migrate_add_exchange_platform()

