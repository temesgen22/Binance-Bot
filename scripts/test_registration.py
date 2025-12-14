"""
Test script to debug registration issues.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
from loguru import logger

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api"

def test_registration(username, email, password, full_name=None):
    """Test user registration with detailed error reporting."""
    logger.info(f"Testing registration with username: {username}, email: {email}")
    
    try:
        response = requests.post(
            f"{API_BASE}/auth/register",
            json={
                "username": username,
                "email": email,
                "password": password,
                "full_name": full_name
            },
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        
        if response.status_code == 201:
            data = response.json()
            logger.success(f"✅ Registration successful! User ID: {data.get('id')}")
            return True
        else:
            try:
                error_data = response.json()
                logger.error(f"❌ Registration failed: {error_data.get('detail', 'Unknown error')}")
            except:
                logger.error(f"❌ Registration failed: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.error("❌ Could not connect to server. Is the API running?")
        logger.info("Start the server with: python -m uvicorn app.main:app --reload")
        return False
    except Exception as e:
        logger.exception(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Registration Test")
    logger.info("=" * 60)
    logger.info("")
    
    # Test with the username that's failing
    test_registration(
        username="teme_2000",
        email="teme.2000@gmail.com",
        password="TestPassword123!",
        full_name="Test User"
    )
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("Check the server logs for detailed error messages")
    logger.info("=" * 60)

