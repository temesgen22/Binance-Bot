"""
Seed script to create default roles in the database.
Run this after migrations to ensure default roles exist.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import init_database, get_db_session
from app.models.db_models import Role
from loguru import logger

logger.info("=" * 60)
logger.info("Seeding Default Roles")
logger.info("=" * 60)
logger.info("")

# Initialize database
init_database()

# Default roles to create
default_roles = [
    {
        "name": "admin",
        "description": "Administrator with full access",
        "is_system": True,
        "permissions": {
            "users": ["create", "read", "update", "delete"],
            "strategies": ["create", "read", "update", "delete"],
            "trades": ["read", "delete"],
            "accounts": ["create", "read", "update", "delete"],
            "backtests": ["read", "delete"],
            "system": ["admin"]
        }
    },
    {
        "name": "user",
        "description": "Regular user with standard access",
        "is_system": True,
        "permissions": {
            "users": ["read", "update"],  # Can read/update own profile
            "strategies": ["create", "read", "update", "delete"],  # Full control over own strategies
            "trades": ["read"],  # Can read own trades
            "accounts": ["create", "read", "update", "delete"],  # Full control over own accounts
            "backtests": ["create", "read", "delete"]  # Can create and manage own backtests
        }
    },
    {
        "name": "read_only",
        "description": "Read-only access",
        "is_system": True,
        "permissions": {
            "users": ["read"],
            "strategies": ["read"],
            "trades": ["read"],
            "accounts": ["read"],
            "backtests": ["read"]
        }
    }
]

with get_db_session() as db:
    created_count = 0
    skipped_count = 0
    
    for role_data in default_roles:
        # Check if role already exists
        existing_role = db.query(Role).filter(Role.name == role_data["name"]).first()
        
        if existing_role:
            logger.info(f"⏭  Role '{role_data['name']}' already exists, skipping...")
            skipped_count += 1
        else:
            role = Role(
                name=role_data["name"],
                description=role_data["description"],
                is_system=role_data["is_system"],
                permissions=role_data["permissions"]
            )
            db.add(role)
            logger.info(f"✓ Created role: {role_data['name']}")
            created_count += 1
    
    db.commit()
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("Summary")
    logger.info("=" * 60)
    logger.info(f"Created: {created_count} role(s)")
    logger.info(f"Skipped: {skipped_count} role(s)")
    logger.info("")
    logger.info("✓ Default roles seeded successfully!")
    logger.info("=" * 60)

