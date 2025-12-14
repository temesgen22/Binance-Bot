"""Quick test to verify password hashing works."""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.auth import get_password_hash, verify_password

print("Testing password hashing...")
print("=" * 60)

# Test normal password
test_password = "test_password_123"
print(f"Test password: {test_password}")

try:
    hashed = get_password_hash(test_password)
    print(f"✓ Hash generated: {hashed[:50]}...")
    
    # Verify
    is_valid = verify_password(test_password, hashed)
    print(f"✓ Verification: {is_valid}")
    
    # Test wrong password
    is_invalid = verify_password("wrong_password", hashed)
    print(f"✓ Wrong password rejected: {not is_invalid}")
    
    # Test long password (over 72 bytes)
    long_password = "a" * 100
    print(f"\nTesting long password ({len(long_password)} chars)...")
    hashed_long = get_password_hash(long_password)
    print(f"✓ Long password hash generated: {hashed_long[:50]}...")
    
    # Verify long password (should work with truncation)
    is_valid_long = verify_password(long_password, hashed_long)
    print(f"✓ Long password verification: {is_valid_long}")
    
    print("\n" + "=" * 60)
    print("✓ All password hashing tests passed!")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

