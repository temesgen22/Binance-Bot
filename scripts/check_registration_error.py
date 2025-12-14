"""
Direct database test to see if we can create a user and what error occurs.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from app.core.database import get_db_session
from app.services.database_service import DatabaseService
from app.core.auth import get_password_hash
from app.models.db_models import User, Role
from datetime import datetime, timezone
import time

print("=" * 60)
print("Direct Database Registration Test")
print("=" * 60)

# Test data
TEST_USERNAME = f"test_user_{int(time.time())}"
TEST_EMAIL = f"test_{int(time.time())}@example.com"
TEST_PASSWORD = "test_password_123"
TEST_FULL_NAME = "Test User"

print(f"Username: {TEST_USERNAME}")
print(f"Email: {TEST_EMAIL}")
print()

try:
    db: Session = next(get_db_session())
    db_service = DatabaseService(db)
    
    # Check if user exists
    existing = db_service.get_user_by_username(TEST_USERNAME)
    if existing:
        print(f"⚠ User {TEST_USERNAME} already exists")
        user = existing
    else:
        # Create user
        print("Creating user in database...")
        password_hash = get_password_hash(TEST_PASSWORD)
        
        user = db_service.create_user(
            username=TEST_USERNAME,
            email=TEST_EMAIL,
            password_hash=password_hash,
            full_name=TEST_FULL_NAME
        )
        print(f"✓ User created: {user.id}")
    
    # Check user object
    print("\nUser object details:")
    print(f"  id: {user.id} (type: {type(user.id)})")
    print(f"  username: {user.username} (type: {type(user.username)})")
    print(f"  email: {user.email} (type: {type(user.email)})")
    print(f"  full_name: {user.full_name} (type: {type(user.full_name)})")
    print(f"  is_active: {user.is_active} (type: {type(user.is_active)})")
    print(f"  is_verified: {user.is_verified} (type: {type(user.is_verified)})")
    print(f"  created_at: {user.created_at} (type: {type(user.created_at)})")
    
    # Try to assign role
    print("\nChecking for 'user' role...")
    user_role = db.query(Role).filter(Role.name == "user").first()
    if user_role:
        print(f"✓ Found role: {user_role.name}")
        if user_role not in user.roles:
            user.roles.append(user_role)
            db.commit()
            db.refresh(user)
            print("✓ Role assigned")
        else:
            print("✓ Role already assigned")
    else:
        print("⚠ 'user' role not found in database")
        print("  Run: python scripts/seed_default_roles.py")
    
    # Try to create UserResponse
    print("\nTesting UserResponse creation...")
    from app.api.routes.auth import UserResponse
    
    try:
        response = UserResponse.from_user(user)
        print("✓ UserResponse created successfully!")
        print(f"  Response ID: {response.id}")
        print(f"  Response username: {response.username}")
        print(f"  Response email: {response.email}")
        print(f"  Response created_at: {response.created_at}")
    except Exception as e:
        print(f"✗ Failed to create UserResponse: {e}")
        import traceback
        traceback.print_exc()
    
    db.close()
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()


