"""
Diagnostic script to check common registration issues.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings
from app.models.db_models import User, Role
from loguru import logger

def check_database():
    """Check database connection and table existence."""
    logger.info("Checking database connection...")
    
    try:
        settings = get_settings()
        engine = create_engine(settings.database_url)
        
        with engine.connect() as conn:
            # Check if users table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'users'
                );
            """))
            users_table_exists = result.scalar()
            
            if not users_table_exists:
                logger.error("❌ 'users' table does not exist!")
                logger.info("💡 Run database migrations: alembic upgrade head")
                return False
            
            logger.success("✅ 'users' table exists")
            
            # Check if roles table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'roles'
                );
            """))
            roles_table_exists = result.scalar()
            
            if not roles_table_exists:
                logger.warning("⚠️  'roles' table does not exist (optional)")
            else:
                logger.success("✅ 'roles' table exists")
                
                # Check if 'user' role exists
                Session = sessionmaker(bind=engine)
                db = Session()
                user_role = db.query(Role).filter(Role.name == "user").first()
                if not user_role:
                    logger.warning("⚠️  'user' role does not exist (will be created if needed)")
                else:
                    logger.success("✅ 'user' role exists")
                db.close()
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        logger.info("💡 Check your DATABASE_URL in .env file")
        logger.info("💡 Make sure PostgreSQL is running")
        return False

def check_existing_user(username, email):
    """Check if username or email already exists."""
    logger.info(f"Checking if user '{username}' or email '{email}' already exists...")
    
    try:
        settings = get_settings()
        engine = create_engine(settings.database_url)
        Session = sessionmaker(bind=engine)
        db = Session()
        
        user_by_username = db.query(User).filter(User.username == username).first()
        user_by_email = db.query(User).filter(User.email == email).first()
        
        if user_by_username:
            logger.error(f"❌ Username '{username}' already exists!")
            logger.info(f"   User ID: {user_by_username.id}")
            logger.info(f"   Created: {user_by_username.created_at}")
            return True
        
        if user_by_email:
            logger.error(f"❌ Email '{email}' already exists!")
            logger.info(f"   Username: {user_by_email.username}")
            logger.info(f"   User ID: {user_by_email.id}")
            return True
        
        logger.success("✅ Username and email are available")
        return False
        
    except Exception as e:
        logger.error(f"❌ Error checking existing users: {e}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Registration Diagnostic Tool")
    logger.info("=" * 60)
    logger.info("")
    
    # Check database
    if not check_database():
        logger.error("")
        logger.error("Database check failed. Please fix database issues first.")
        sys.exit(1)
    
    logger.info("")
    
    # Check for existing user
    username = "teme_2000"
    email = "teme.2000@gmail.com"
    
    if check_existing_user(username, email):
        logger.error("")
        logger.error("User already exists. Try a different username or email.")
        sys.exit(1)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ All checks passed! Registration should work.")
    logger.info("=" * 60)
    logger.info("")
    logger.info("If registration still fails, check:")
    logger.info("1. Server logs for detailed error messages")
    logger.info("2. Browser console for JavaScript errors")
    logger.info("3. Network tab in browser DevTools for API response")

