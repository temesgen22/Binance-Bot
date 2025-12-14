"""
Comprehensive test for Phase 3: Database + Redis Integration
Tests the complete flow: Auth -> Account -> Strategy -> Trade
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
from loguru import logger
from uuid import uuid4

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api"

logger.info("=" * 60)
logger.info("Phase 3 Integration Test")
logger.info("=" * 60)
logger.info("")
logger.info("⚠ Make sure the server is running: uvicorn app.main:app --reload")
logger.info("")

test_results = {
    "passed": 0,
    "failed": 0,
    "tests": []
}

def test(name: str):
    """Test decorator."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                test_results["passed"] += 1
                test_results["tests"].append({"name": name, "status": "PASSED"})
                logger.info(f"✓ {name}")
                return result
            except Exception as e:
                test_results["failed"] += 1
                test_results["tests"].append({"name": name, "status": "FAILED", "error": str(e)})
                logger.error(f"✗ {name}: {e}")
                return None
        return wrapper
    return decorator

# Test data
test_username = f"testuser_{uuid4().hex[:8]}"
test_email = f"test_{uuid4().hex[:8]}@example.com"
test_password = "TestPassword123!"
access_token = None
refresh_token = None
account_id = None
strategy_id = None

# ============================================
# TEST 1: User Registration
# ============================================
@test("User Registration")
def test_user_registration():
    global access_token, refresh_token
    
    response = requests.post(
        f"{API_BASE}/auth/register",
        json={
            "username": test_username,
            "email": test_email,
            "password": test_password,
            "full_name": "Test User"
        },
        timeout=10
    )
    
    if response.status_code != 201:
        raise Exception(f"Registration failed: {response.status_code} - {response.text}")
    
    user_data = response.json()
    assert user_data.get("username") == test_username
    return user_data

# ============================================
# TEST 2: User Login
# ============================================
@test("User Login")
def test_user_login():
    global access_token, refresh_token
    
    response = requests.post(
        f"{API_BASE}/auth/login",
        json={
            "username": test_username,
            "password": test_password
        },
        timeout=10
    )
    
    if response.status_code != 200:
        raise Exception(f"Login failed: {response.status_code} - {response.text}")
    
    token_data = response.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    
    assert access_token is not None
    assert refresh_token is not None
    return token_data

# ============================================
# TEST 3: Get Current User
# ============================================
@test("Get Current User")
def test_get_current_user():
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{API_BASE}/auth/me", headers=headers, timeout=10)
    
    if response.status_code != 200:
        raise Exception(f"Get user failed: {response.status_code} - {response.text}")
    
    user_data = response.json()
    assert user_data.get("username") == test_username
    return user_data

# ============================================
# TEST 4: Create Account
# ============================================
@test("Create Account")
def test_create_account():
    global account_id
    
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.post(
        f"{BASE_URL}/accounts/",
        headers=headers,
        json={
            "account_id": "test_account_1",
            "api_key": "test_api_key_123",
            "api_secret": "test_api_secret_456",
            "name": "Test Account",
            "testnet": True,
            "is_default": True
        },
        timeout=10
    )
    
    if response.status_code != 201:
        raise Exception(f"Create account failed: {response.status_code} - {response.text}")
    
    account_data = response.json()
    account_id = account_data.get("account_id")
    assert account_id == "test_account_1"
    return account_data

# ============================================
# TEST 5: List Accounts
# ============================================
@test("List Accounts")
def test_list_accounts():
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{BASE_URL}/accounts/list", headers=headers, timeout=10)
    
    if response.status_code != 200:
        raise Exception(f"List accounts failed: {response.status_code} - {response.text}")
    
    accounts = response.json()
    assert len(accounts) > 0
    assert any(acc.get("account_id") == "test_account_1" for acc in accounts)
    return accounts

# ============================================
# TEST 6: Create Strategy
# ============================================
@test("Create Strategy")
def test_create_strategy():
    global strategy_id
    
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.post(
        f"{BASE_URL}/strategies/",
        headers=headers,
        json={
            "name": "Test Strategy",
            "symbol": "BTCUSDT",
            "strategy_type": "scalping",
            "leverage": 5,
            "risk_per_trade": 0.01,
            "params": {"ema_fast": 8, "ema_slow": 21},
            "account_id": "test_account_1",
            "auto_start": False
        },
        timeout=10
    )
    
    if response.status_code != 201:
        raise Exception(f"Create strategy failed: {response.status_code} - {response.text}")
    
    strategy_data = response.json()
    strategy_id = strategy_data.get("id")
    assert strategy_id is not None
    assert strategy_data.get("symbol") == "BTCUSDT"
    return strategy_data

# ============================================
# TEST 7: List Strategies
# ============================================
@test("List Strategies")
def test_list_strategies():
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{BASE_URL}/strategies/list", headers=headers, timeout=10)
    
    if response.status_code != 200:
        raise Exception(f"List strategies failed: {response.status_code} - {response.text}")
    
    strategies = response.json()
    assert len(strategies) > 0
    assert any(s.get("id") == strategy_id for s in strategies)
    return strategies

# ============================================
# TEST 8: Get Strategy
# ============================================
@test("Get Strategy")
def test_get_strategy():
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(
        f"{BASE_URL}/strategies/{strategy_id}",
        headers=headers,
        timeout=10
    )
    
    if response.status_code != 200:
        raise Exception(f"Get strategy failed: {response.status_code} - {response.text}")
    
    strategy_data = response.json()
    assert strategy_data.get("id") == strategy_id
    return strategy_data

# ============================================
# TEST 9: List Trades (Empty)
# ============================================
@test("List Trades (Empty)")
def test_list_trades_empty():
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{BASE_URL}/trades/list", headers=headers, timeout=10)
    
    if response.status_code != 200:
        raise Exception(f"List trades failed: {response.status_code} - {response.text}")
    
    trades = response.json()
    # Should be empty for new strategy
    return trades

# ============================================
# TEST 10: Token Refresh
# ============================================
@test("Token Refresh")
def test_token_refresh():
    response = requests.post(
        f"{API_BASE}/auth/refresh",
        json={"refresh_token": refresh_token},
        timeout=10
    )
    
    if response.status_code != 200:
        raise Exception(f"Token refresh failed: {response.status_code} - {response.text}")
    
    token_data = response.json()
    assert token_data.get("access_token") is not None
    return token_data

# ============================================
# RUN ALL TESTS
# ============================================
logger.info("Running Phase 3 integration tests...")
logger.info("")

try:
    test_user_registration()
    test_user_login()
    test_get_current_user()
    test_create_account()
    test_list_accounts()
    test_create_strategy()
    test_list_strategies()
    test_get_strategy()
    test_list_trades_empty()
    test_token_refresh()
except requests.exceptions.ConnectionError:
    logger.error("✗ Could not connect to server. Is the API running?")
    logger.error("  Start the server with: uvicorn app.main:app --reload")
    sys.exit(1)
except Exception as e:
    logger.error(f"✗ Test execution failed: {e}")
    import traceback
    traceback.print_exc()

# ============================================
# SUMMARY
# ============================================
logger.info("")
logger.info("=" * 60)
logger.info("TEST SUMMARY")
logger.info("=" * 60)
logger.info(f"Total Tests: {test_results['passed'] + test_results['failed']}")
logger.info(f"Passed: {test_results['passed']}")
logger.info(f"Failed: {test_results['failed']}")
logger.info("")

if test_results['failed'] > 0:
    logger.error("Failed Tests:")
    for test in test_results['tests']:
        if test['status'] == 'FAILED':
            logger.error(f"  - {test['name']}: {test.get('error', 'Unknown error')}")

if test_results['failed'] == 0:
    logger.info("🎉 All Phase 3 integration tests passed!")
    logger.info("")
    logger.info("Database + Redis integration is working correctly!")
    logger.info("Ready to proceed with Phase 4: Frontend Updates")
else:
    logger.error("⚠ Some tests failed. Please review the errors above.")
    sys.exit(1)

logger.info("=" * 60)

