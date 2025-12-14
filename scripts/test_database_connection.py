"""
Test script to verify database connection and basic operations.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import init_database, get_db_session
from app.models.db_models import User, Role
from loguru import logger

def test_connection():
    """Test database connection."""
    try:
        logger.info("Initializing database...")
        init_database()
        logger.info("✓ Database initialized successfully")
        
        # Test query
        with get_db_session() as db:
            user_count = db.query(User).count()
            logger.info(f"✓ Database connection working. Found {user_count} users")
            
            role_count = db.query(Role).count()
            logger.info(f"✓ Found {role_count} roles")
        
        logger.info("✓ All database tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"✗ Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)

