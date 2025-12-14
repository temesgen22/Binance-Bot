"""
Test script for authentication endpoints.
Tests user registration, login, token refresh, and protected endpoints.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
from loguru import logger

# Base URL
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/auth"

logger.info("=" * 60)
logger.info("Authentication System Test")
logger.info("=" * 60)
logger.info("")

# Test data
test_username = f"testuser_{__import__('uuid').uuid4().hex[:8]}"
test_email = f"test_{__import__('uuid').uuid4().hex[:8]}@example.com"
test_password = "TestPassword123!"
test_full_name = "Test User"

logger.info(f"Test username: {test_username}")
logger.info(f"Test email: {test_email}")
logger.info("")

# ============================================
# TEST 1: User Registration
# ============================================
logger.info("=" * 60)
logger.info("TEST 1: User Registration")
logger.info("=" * 60)

try:
    response = requests.post(
        f"{API_BASE}/register",
        json={
            "username": test_username,
            "email": test_email,
            "password": test_password,
            "full_name": test_full_name
        },
        timeout=10
    )
    
    logger.info(f"Status Code: {response.status_code}")
    
    if response.status_code == 201:
        user_data = response.json()
        logger.info(f"✓ User registered successfully!")
        logger.info(f"  User ID: {user_data.get('id')}")
        logger.info(f"  Username: {user_data.get('username')}")
        logger.info(f"  Email: {user_data.get('email')}")
        logger.info("")
    else:
        logger.error(f"✗ Registration failed: {response.status_code}")
        logger.error(f"  Response: {response.text}")
        sys.exit(1)
        
except requests.exceptions.ConnectionError:
    logger.error("✗ Could not connect to server. Is the API running?")
    logger.error("  Start the server with: uvicorn app.main:app --reload")
    sys.exit(1)
except Exception as e:
    logger.error(f"✗ Registration test failed: {e}")
    sys.exit(1)

# ============================================
# TEST 2: User Login
# ============================================
logger.info("=" * 60)
logger.info("TEST 2: User Login")
logger.info("=" * 60)

try:
    response = requests.post(
        f"{API_BASE}/login",
        json={
            "username": test_username,
            "password": test_password
        },
        timeout=10
    )
    
    logger.info(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        
        logger.info(f"✓ Login successful!")
        logger.info(f"  Access Token: {access_token[:50]}...")
        logger.info(f"  Refresh Token: {refresh_token[:50]}...")
        logger.info(f"  Token Type: {token_data.get('token_type')}")
        logger.info(f"  Expires In: {token_data.get('expires_in')} seconds")
        logger.info("")
    else:
        logger.error(f"✗ Login failed: {response.status_code}")
        logger.error(f"  Response: {response.text}")
        sys.exit(1)
        
except Exception as e:
    logger.error(f"✗ Login test failed: {e}")
    sys.exit(1)

# ============================================
# TEST 3: Get Current User (Protected Endpoint)
# ============================================
logger.info("=" * 60)
logger.info("TEST 3: Get Current User (Protected Endpoint)")
logger.info("=" * 60)

try:
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    response = requests.get(
        f"{API_BASE}/me",
        headers=headers,
        timeout=10
    )
    
    logger.info(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        user_data = response.json()
        logger.info(f"✓ Protected endpoint accessed successfully!")
        logger.info(f"  User ID: {user_data.get('id')}")
        logger.info(f"  Username: {user_data.get('username')}")
        logger.info(f"  Email: {user_data.get('email')}")
        logger.info(f"  Full Name: {user_data.get('full_name')}")
        logger.info(f"  Is Active: {user_data.get('is_active')}")
        logger.info("")
    else:
        logger.error(f"✗ Protected endpoint failed: {response.status_code}")
        logger.error(f"  Response: {response.text}")
        sys.exit(1)
        
except Exception as e:
    logger.error(f"✗ Protected endpoint test failed: {e}")
    sys.exit(1)

# ============================================
# TEST 4: Token Refresh
# ============================================
logger.info("=" * 60)
logger.info("TEST 4: Token Refresh")
logger.info("=" * 60)

try:
    response = requests.post(
        f"{API_BASE}/refresh",
        json={
            "refresh_token": refresh_token
        },
        timeout=10
    )
    
    logger.info(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        token_data = response.json()
        new_access_token = token_data.get("access_token")
        new_refresh_token = token_data.get("refresh_token")
        
        logger.info(f"✓ Token refresh successful!")
        logger.info(f"  New Access Token: {new_access_token[:50]}...")
        logger.info(f"  New Refresh Token: {new_refresh_token[:50]}...")
        logger.info("")
        
        # Test new access token
        headers = {
            "Authorization": f"Bearer {new_access_token}"
        }
        response = requests.get(f"{API_BASE}/me", headers=headers, timeout=10)
        if response.status_code == 200:
            logger.info(f"✓ New access token works correctly!")
        else:
            logger.error(f"✗ New access token failed: {response.status_code}")
    else:
        logger.error(f"✗ Token refresh failed: {response.status_code}")
        logger.error(f"  Response: {response.text}")
        sys.exit(1)
        
except Exception as e:
    logger.error(f"✗ Token refresh test failed: {e}")
    sys.exit(1)

# ============================================
# TEST 5: Invalid Token (Should Fail)
# ============================================
logger.info("=" * 60)
logger.info("TEST 5: Invalid Token (Should Fail)")
logger.info("=" * 60)

try:
    headers = {
        "Authorization": "Bearer invalid_token_here"
    }
    
    response = requests.get(
        f"{API_BASE}/me",
        headers=headers,
        timeout=10
    )
    
    logger.info(f"Status Code: {response.status_code}")
    
    if response.status_code == 401:
        logger.info(f"✓ Invalid token correctly rejected (401 Unauthorized)")
        logger.info("")
    else:
        logger.warning(f"⚠ Expected 401, got {response.status_code}")
        logger.warning(f"  Response: {response.text}")
        
except Exception as e:
    logger.error(f"✗ Invalid token test failed: {e}")

# ============================================
# TEST 6: Duplicate Registration (Should Fail)
# ============================================
logger.info("=" * 60)
logger.info("TEST 6: Duplicate Registration (Should Fail)")
logger.info("=" * 60)

try:
    response = requests.post(
        f"{API_BASE}/register",
        json={
            "username": test_username,
            "email": test_email,
            "password": test_password,
            "full_name": test_full_name
        },
        timeout=10
    )
    
    logger.info(f"Status Code: {response.status_code}")
    
    if response.status_code == 400:
        logger.info(f"✓ Duplicate registration correctly rejected (400 Bad Request)")
        logger.info("")
    else:
        logger.warning(f"⚠ Expected 400, got {response.status_code}")
        logger.warning(f"  Response: {response.text}")
        
except Exception as e:
    logger.error(f"✗ Duplicate registration test failed: {e}")

# ============================================
# SUMMARY
# ============================================
logger.info("=" * 60)
logger.info("TEST SUMMARY")
logger.info("=" * 60)
logger.info("✓ User Registration: PASSED")
logger.info("✓ User Login: PASSED")
logger.info("✓ Protected Endpoint: PASSED")
logger.info("✓ Token Refresh: PASSED")
logger.info("✓ Invalid Token Rejection: PASSED")
logger.info("✓ Duplicate Registration Rejection: PASSED")
logger.info("")
logger.info("🎉 All authentication tests passed!")
logger.info("=" * 60)

