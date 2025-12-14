"""
Debug script to test user registration and see detailed error messages.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
import time
from uuid import uuid4

BASE_URL = "http://127.0.0.1:8000"
API_BASE = f"{BASE_URL}/api"

# Test data
TEST_USERNAME = f"test_user_{int(time.time())}"
TEST_EMAIL = f"test_{int(time.time())}@example.com"
TEST_PASSWORD = "test_password_123"
TEST_FULL_NAME = "Test User"

print("=" * 60)
print("Registration Debug Test")
print("=" * 60)
print(f"Username: {TEST_USERNAME}")
print(f"Email: {TEST_EMAIL}")
print(f"Password: {TEST_PASSWORD}")
print()

try:
    print("Sending registration request...")
    response = requests.post(
        f"{API_BASE}/auth/register",
        json={
            "username": TEST_USERNAME,
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "full_name": TEST_FULL_NAME
        },
        timeout=10
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print()
    
    try:
        response_data = response.json()
        print("Response JSON:")
        import json
        print(json.dumps(response_data, indent=2))
    except:
        print("Response Text:")
        print(response.text)
    
    if response.status_code == 201:
        print("\n✓ Registration successful!")
    else:
        print(f"\n✗ Registration failed with status {response.status_code}")
        
except requests.exceptions.RequestException as e:
    print(f"\n✗ Request failed: {e}")
    import traceback
    traceback.print_exc()


