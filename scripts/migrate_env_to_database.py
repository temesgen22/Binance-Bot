"""
Migration script to migrate .env file accounts to database.
This script:
1. Reads accounts from .env file
2. Finds or creates user with email teme.2000@gmail.com
3. Migrates all .env accounts to database
4. Sets the first account as default
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import get_db_session
from app.core.config import get_settings
from app.services.database_service import DatabaseService
from app.core.auth import get_password_hash
from app.models.db_models import User, Account
from loguru import logger
import re


def load_env_accounts():
    """Load accounts from .env file."""
    # Load .env file
    env_file = project_root / ".env"
    if not env_file.exists():
        logger.warning(f".env file not found at {env_file}")
        return []
    
    load_dotenv(env_file)
    
    accounts = []
    
    # Load default account
    default_api_key = os.environ.get("BINANCE_API_KEY")
    default_api_secret = os.environ.get("BINANCE_API_SECRET")
    default_testnet = os.environ.get("BINANCE_TESTNET", "true").lower() in ("true", "1", "yes")
    
    if default_api_key and default_api_secret and default_api_key != "demo":
        accounts.append({
            "account_id": "default",
            "api_key": default_api_key,
            "api_secret": default_api_secret,
            "testnet": default_testnet,
            "name": "Default Account",
            "exchange_platform": "binance"
        })
    
    # Load additional accounts from BINANCE_ACCOUNT_* pattern
    pattern = re.compile(r'^BINANCE_ACCOUNT_([A-Za-z0-9_]+)_API_KEY$')
    for env_key in os.environ.keys():
        match = pattern.match(env_key)
        if match:
            account_id = match.group(1).lower()
            api_key = os.environ.get(env_key)
            secret_key = f"BINANCE_ACCOUNT_{match.group(1)}_API_SECRET"
            api_secret = os.environ.get(secret_key)
            
            if not api_secret:
                logger.warning(f"Found {env_key} but missing {secret_key}, skipping")
                continue
            
            name_key = f"BINANCE_ACCOUNT_{match.group(1)}_NAME"
            account_name = os.environ.get(name_key, account_id.title())
            
            testnet_key = f"BINANCE_ACCOUNT_{match.group(1)}_TESTNET"
            testnet_str = os.environ.get(testnet_key, "").lower()
            account_testnet = default_testnet  # Default to global setting
            if testnet_str in ("true", "1", "yes"):
                account_testnet = True
            elif testnet_str in ("false", "0", "no"):
                account_testnet = False
            
            accounts.append({
                "account_id": account_id,
                "api_key": api_key,
                "api_secret": api_secret,
                "testnet": account_testnet,
                "name": account_name,
                "exchange_platform": "binance"
            })
    
    return accounts


def get_or_create_user(db: Session, email: str) -> User:
    """Get or create user with given email."""
    db_service = DatabaseService(db)
    user = db_service.get_user_by_email(email)
    
    if user:
        logger.info(f"Found existing user: {email}")
        return user
    
    # Create new user
    username = email.split("@")[0]  # Use email prefix as username
    password_hash = get_password_hash("changeme123")  # Default password - user should change
    
    user = db_service.create_user(
        username=username,
        email=email,
        password_hash=password_hash,
        full_name=email
    )
    
    logger.info(f"Created new user: {email} (username: {username})")
    logger.warning(f"⚠️  Default password set to 'changeme123' - user should change it!")
    
    return user


def migrate_accounts_to_database():
    """Migrate .env accounts to database for teme.2000@gmail.com."""
    from app.core.database import init_database
    
    # Initialize database connection
    init_database()
    
    with get_db_session() as db:
        try:
            # Get or create user
            user = get_or_create_user(db, "teme.2000@gmail.com")
            
            # Load accounts from .env
            env_accounts = load_env_accounts()
            
            if not env_accounts:
                logger.warning("No accounts found in .env file to migrate")
                return
            
            logger.info(f"Found {len(env_accounts)} account(s) in .env file")
            
            db_service = DatabaseService(db)
            migrated_count = 0
            skipped_count = 0
            
            # Migrate each account
            for i, account_data in enumerate(env_accounts):
                account_id = account_data["account_id"]
                
                # Check if account already exists
                existing = db_service.get_account_by_id(user.id, account_id)
                if existing:
                    logger.warning(f"Account '{account_id}' already exists in database, skipping")
                    skipped_count += 1
                    continue
                
                # Create account in database
                try:
                    db_service.create_account(
                        user_id=user.id,
                        account_id=account_id,
                        api_key_encrypted=account_data["api_key"],  # Store as-is (encryption can be added later)
                        api_secret_encrypted=account_data["api_secret"],
                        name=account_data["name"],
                        exchange_platform=account_data.get("exchange_platform", "binance"),
                        testnet=account_data["testnet"],
                        is_default=(i == 0)  # First account is default
                    )
                    logger.info(f"✅ Migrated account: {account_id} ({account_data['name']})")
                    migrated_count += 1
                except Exception as e:
                    logger.error(f"❌ Failed to migrate account {account_id}: {e}")
                    continue
            
            db.commit()
            logger.info(f"\n✅ Migration complete!")
            logger.info(f"   - Migrated: {migrated_count} account(s)")
            logger.info(f"   - Skipped: {skipped_count} account(s) (already exist)")
            logger.info(f"   - User: {user.email}")
            logger.info(f"\n⚠️  Note: API keys are stored in database. Consider removing them from .env file after verification.")
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Migration failed: {e}")
            raise


if __name__ == "__main__":
    migrate_accounts_to_database()

