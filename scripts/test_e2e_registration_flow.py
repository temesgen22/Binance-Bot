"""
End-to-End Test: User Registration → Login → Strategy Creation → Database Verification

This test verifies the complete flow:
1. User registration via API
2. Database verification (user exists)
3. User login
4. Account creation (if needed)
5. Strategy creation
6. Database verification (strategy exists)
7. Strategy listing
8. Data persistence verification

Run this test to ensure the entire registration and strategy creation flow works correctly.
"""
import sys
import os
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
from uuid import uuid4
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.services.database_service import DatabaseService
from app.models.db_models import User, Strategy, Account
from app.core.auth import verify_password


# Test configuration
BASE_URL = "http://127.0.0.1:8000"
API_BASE = f"{BASE_URL}/api"

# Test data
TEST_USERNAME = f"test_user_{int(time.time())}"
TEST_EMAIL = f"test_{int(time.time())}@example.com"
TEST_PASSWORD = "test_password_123"
TEST_FULL_NAME = "Test User"

TEST_ACCOUNT_ID = "test_account_1"
TEST_ACCOUNT_NAME = "Test Account"

TEST_STRATEGY_NAME = f"Test Strategy {int(time.time())}"
TEST_SYMBOL = "BTCUSDT"
TEST_STRATEGY_TYPE = "scalping"
TEST_LEVERAGE = 5
TEST_RISK_PER_TRADE = 0.01


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_step(step_num: int, description: str):
    """Print a test step header."""
    print(f"\n{Colors.BLUE}{Colors.BOLD}Step {step_num}: {description}{Colors.RESET}")
    print("-" * 60)


def print_success(message: str):
    """Print a success message."""
    print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")


def print_error(message: str):
    """Print an error message."""
    print(f"{Colors.RED}✗ {message}{Colors.RESET}")


def print_warning(message: str):
    """Print a warning message."""
    print(f"{Colors.YELLOW}⚠ {message}{Colors.RESET}")


def print_info(message: str):
    """Print an info message."""
    print(f"{Colors.BLUE}ℹ {message}{Colors.RESET}")


def check_api_running() -> bool:
    """Check if the API server is running."""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def test_user_registration() -> dict:
    """Test 1: User Registration via API"""
    print_step(1, "User Registration via API")
    
    print_info(f"Registering user: {TEST_USERNAME}")
    print_info(f"Email: {TEST_EMAIL}")
    
    try:
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
        
        if response.status_code == 201:
            user_data = response.json()
            print_success(f"User registered successfully!")
            print_info(f"User ID: {user_data.get('id')}")
            print_info(f"Username: {user_data.get('username')}")
            print_info(f"Email: {user_data.get('email')}")
            return user_data
        else:
            error_detail = response.json().get('detail', 'Unknown error')
            print_error(f"Registration failed: {error_detail}")
            print_error(f"Status code: {response.status_code}")
            print_error(f"Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        return None


def test_database_user_verification(user_id: str) -> bool:
    """Test 2: Verify User Exists in Database"""
    print_step(2, "Database Verification: User Exists")
    
    try:
        db: Session = next(get_db_session())
        db_service = DatabaseService(db)
        
        # Get user by ID
        user = db_service.get_user_by_id(user_id)
        if user:
            print_success(f"User found in database!")
            print_info(f"Database User ID: {user.id}")
            print_info(f"Database Username: {user.username}")
            print_info(f"Database Email: {user.email}")
            print_info(f"Database Full Name: {user.full_name}")
            print_info(f"Is Active: {user.is_active}")
            print_info(f"Created At: {user.created_at}")
            
            # Verify password hash
            if verify_password(TEST_PASSWORD, user.password_hash):
                print_success("Password hash verification: PASSED")
            else:
                print_error("Password hash verification: FAILED")
                return False
            
            # Verify roles
            if user.roles:
                print_info(f"User has {len(user.roles)} role(s):")
                for role in user.roles:
                    print_info(f"  - {role.name}")
            else:
                print_warning("User has no roles assigned")
            
            return True
        else:
            print_error("User NOT found in database!")
            return False
            
    except Exception as e:
        print_error(f"Database verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_user_login() -> dict:
    """Test 3: User Login"""
    print_step(3, "User Login")
    
    print_info(f"Logging in as: {TEST_USERNAME}")
    
    try:
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD
            },
            timeout=10
        )
        
        if response.status_code == 200:
            token_data = response.json()
            print_success("Login successful!")
            print_info(f"Access token received: {token_data.get('access_token', '')[:50]}...")
            print_info(f"Token type: {token_data.get('token_type')}")
            return token_data
        else:
            error_detail = response.json().get('detail', 'Unknown error')
            print_error(f"Login failed: {error_detail}")
            print_error(f"Status code: {response.status_code}")
            return None
            
    except requests.exceptions.RequestException as e:
        print_error(f"Login request failed: {e}")
        return None


def test_get_current_user(access_token: str) -> dict:
    """Test 4: Get Current User Info"""
    print_step(4, "Get Current User Info")
    
    try:
        response = requests.get(
            f"{API_BASE}/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            user_data = response.json()
            print_success("User info retrieved successfully!")
            print_info(f"User ID: {user_data.get('id')}")
            print_info(f"Username: {user_data.get('username')}")
            print_info(f"Email: {user_data.get('email')}")
            return user_data
        else:
            print_error(f"Failed to get user info: {response.status_code}")
            print_error(f"Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        return None


def test_list_accounts(access_token: str) -> list:
    """Test 5: List User Accounts"""
    print_step(5, "List User Accounts")
    
    try:
        response = requests.get(
            f"{API_BASE}/accounts/list",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            accounts = response.json()
            print_success(f"Found {len(accounts)} account(s)")
            for account in accounts:
                print_info(f"  - {account.get('account_id')} ({account.get('name', 'No name')})")
            return accounts
        else:
            print_warning(f"Failed to list accounts: {response.status_code}")
            print_warning("This is OK if no accounts are configured yet")
            return []
            
    except requests.exceptions.RequestException as e:
        print_warning(f"Request failed: {e}")
        return []


def test_create_account(access_token: str) -> dict:
    """Test 6: Create Test Account (if needed)"""
    print_step(6, "Create Test Account")
    
    # Check if account already exists
    existing_accounts = test_list_accounts(access_token)
    for account in existing_accounts:
        if account.get('account_id') == TEST_ACCOUNT_ID:
            print_info(f"Account '{TEST_ACCOUNT_ID}' already exists, skipping creation")
            return account
    
    print_info("Creating test account...")
    print_warning("Note: This requires valid Binance API credentials")
    print_warning("For testing, we'll use placeholder encrypted values")
    
    try:
        # Note: In a real scenario, API keys should be encrypted
        # For testing, we'll use placeholder values
        response = requests.post(
            f"{API_BASE}/accounts/",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "account_id": TEST_ACCOUNT_ID,
                "name": TEST_ACCOUNT_NAME,
                "api_key_encrypted": "test_encrypted_key",
                "api_secret_encrypted": "test_encrypted_secret",
                "testnet": True,
                "is_default": True
            },
            timeout=10
        )
        
        if response.status_code == 201:
            account_data = response.json()
            print_success("Account created successfully!")
            print_info(f"Account ID: {account_data.get('account_id')}")
            return account_data
        else:
            error_detail = response.json().get('detail', 'Unknown error')
            print_warning(f"Account creation failed: {error_detail}")
            print_warning("This is OK if accounts are managed differently")
            print_warning("We'll use 'default' account for strategy creation")
            return None
            
    except requests.exceptions.RequestException as e:
        print_warning(f"Request failed: {e}")
        print_warning("We'll use 'default' account for strategy creation")
        return None


def test_create_strategy(access_token: str, account_id: str = "default") -> dict:
    """Test 7: Create Strategy"""
    print_step(7, "Create Strategy")
    
    print_info(f"Creating strategy: {TEST_STRATEGY_NAME}")
    print_info(f"Symbol: {TEST_SYMBOL}")
    print_info(f"Type: {TEST_STRATEGY_TYPE}")
    print_info(f"Leverage: {TEST_LEVERAGE}x")
    print_info(f"Account: {account_id}")
    
    strategy_data = {
        "name": TEST_STRATEGY_NAME,
        "symbol": TEST_SYMBOL,
        "strategy_type": TEST_STRATEGY_TYPE,
        "leverage": TEST_LEVERAGE,
        "risk_per_trade": TEST_RISK_PER_TRADE,
        "max_positions": 1,
        "account_id": account_id,
        "auto_start": False,
        "params": {
            "kline_interval": "1m",
            "ema_fast": 8,
            "ema_slow": 21,
            "take_profit_pct": 0.004,
            "stop_loss_pct": 0.002,
            "enable_short": True,
            "min_ema_separation": 0.0002,
            "enable_htf_bias": True,
            "cooldown_candles": 2,
            "enable_ema_cross_exit": True,
            "trailing_stop_enabled": False,
            "trailing_stop_activation_pct": 0.0
        }
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/strategies/",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json=strategy_data,
            timeout=30
        )
        
        if response.status_code == 201:
            strategy = response.json()
            print_success("Strategy created successfully!")
            print_info(f"Strategy ID: {strategy.get('id')}")
            print_info(f"Strategy Name: {strategy.get('name')}")
            print_info(f"Status: {strategy.get('status')}")
            print_info(f"Symbol: {strategy.get('symbol')}")
            print_info(f"Leverage: {strategy.get('leverage')}x")
            return strategy
        else:
            error_detail = response.json().get('detail', 'Unknown error')
            print_error(f"Strategy creation failed: {error_detail}")
            print_error(f"Status code: {response.status_code}")
            print_error(f"Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_database_strategy_verification(strategy_id: str, user_id: str) -> bool:
    """Test 8: Verify Strategy Exists in Database"""
    print_step(8, "Database Verification: Strategy Exists")
    
    try:
        db: Session = next(get_db_session())
        db_service = DatabaseService(db)
        
        # Get strategy from database
        strategy = db.query(Strategy).filter(
            Strategy.strategy_id == strategy_id,
            Strategy.user_id == user_id
        ).first()
        
        if strategy:
            print_success("Strategy found in database!")
            print_info(f"Database Strategy ID: {strategy.id}")
            print_info(f"Strategy ID (UUID): {strategy.strategy_id}")
            print_info(f"Strategy Name: {strategy.name}")
            print_info(f"Symbol: {strategy.symbol}")
            print_info(f"Strategy Type: {strategy.strategy_type}")
            print_info(f"Leverage: {strategy.leverage}x")
            print_info(f"Risk Per Trade: {strategy.risk_per_trade}")
            print_info(f"Status: {strategy.status}")
            print_info(f"User ID: {strategy.user_id}")
            print_info(f"Account ID: {strategy.account_id}")
            print_info(f"Created At: {strategy.created_at}")
            
            # Verify params
            if strategy.params:
                print_info(f"Parameters: {len(strategy.params)} keys")
                print_info(f"  - kline_interval: {strategy.params.get('kline_interval')}")
                print_info(f"  - ema_fast: {strategy.params.get('ema_fast')}")
                print_info(f"  - ema_slow: {strategy.params.get('ema_slow')}")
            
            return True
        else:
            print_error("Strategy NOT found in database!")
            print_error(f"Searched for strategy_id={strategy_id}, user_id={user_id}")
            
            # List all strategies for this user
            all_strategies = db.query(Strategy).filter(Strategy.user_id == user_id).all()
            print_info(f"Found {len(all_strategies)} strategies for this user:")
            for s in all_strategies:
                print_info(f"  - {s.strategy_id} ({s.name})")
            
            return False
            
    except Exception as e:
        print_error(f"Database verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_list_strategies(access_token: str) -> list:
    """Test 9: List User Strategies"""
    print_step(9, "List User Strategies")
    
    try:
        response = requests.get(
            f"{API_BASE}/strategies/list",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            strategies = response.json()
            print_success(f"Found {len(strategies)} strategy(ies)")
            for strategy in strategies:
                print_info(f"  - {strategy.get('name')} ({strategy.get('symbol')}) - {strategy.get('status')}")
            return strategies
        else:
            print_error(f"Failed to list strategies: {response.status_code}")
            print_error(f"Response: {response.text}")
            return []
            
    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        return None


def test_data_persistence(access_token: str, user_id: str, strategy_id: str) -> bool:
    """Test 10: Verify Data Persistence (re-fetch from API)"""
    print_step(10, "Data Persistence Verification")
    
    try:
        # List all strategies and find ours
        response = requests.get(
            f"{API_BASE}/strategies/list",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            print_error(f"Failed to list strategies: {response.status_code}")
            return False
        
        strategies = response.json()
        strategy = next((s for s in strategies if s.get('id') == strategy_id), None)
        
        if not strategy:
            print_error(f"Strategy {strategy_id} not found in list")
            return False
        
        # Now verify the data
        
        print_success("Strategy retrieved successfully from API!")
        print_info(f"Strategy ID: {strategy.get('id')}")
        print_info(f"Name: {strategy.get('name')}")
        print_info(f"Status: {strategy.get('status')}")
        
        # Verify all data matches
        if strategy.get('name') == TEST_STRATEGY_NAME:
            print_success("Strategy name matches")
        else:
            print_error(f"Strategy name mismatch: expected '{TEST_STRATEGY_NAME}', got '{strategy.get('name')}'")
            return False
        
        if strategy.get('symbol') == TEST_SYMBOL:
            print_success("Symbol matches")
        else:
            print_error(f"Symbol mismatch: expected '{TEST_SYMBOL}', got '{strategy.get('symbol')}'")
            return False
        
        if strategy.get('leverage') == TEST_LEVERAGE:
            print_success("Leverage matches")
        else:
            print_error(f"Leverage mismatch: expected {TEST_LEVERAGE}, got {strategy.get('leverage')}")
            return False
        
        return True
            
    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        return False


def main():
    """Run all end-to-end tests."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print("End-to-End Test: Registration → Strategy Creation → Database")
    print(f"{'='*60}{Colors.RESET}\n")
    
    # Check if API is running
    print_info("Checking if API server is running...")
    if not check_api_running():
        print_error("API server is not running!")
        print_error(f"Please start the server: uvicorn app.main:app --reload")
        print_error(f"Then run this test again.")
        return False
    
    print_success("API server is running!")
    
    # Track results
    results = {
        "user_registration": False,
        "database_user_verification": False,
        "user_login": False,
        "get_current_user": False,
        "list_accounts": False,
        "create_account": None,
        "create_strategy": False,
        "database_strategy_verification": False,
        "list_strategies": False,
        "data_persistence": False
    }
    
    user_id = None
    access_token = None
    strategy_id = None
    
    try:
        # Test 1: User Registration
        user_data = test_user_registration()
        if user_data:
            results["user_registration"] = True
            user_id = user_data.get('id')
        else:
            print_error("Cannot continue without user registration")
            return False
        
        # Test 2: Database User Verification
        if user_id:
            results["database_user_verification"] = test_database_user_verification(user_id)
        
        # Test 3: User Login
        token_data = test_user_login()
        if token_data:
            results["user_login"] = True
            access_token = token_data.get('access_token')
        else:
            print_error("Cannot continue without login")
            return False
        
        # Test 4: Get Current User
        if access_token:
            user_info = test_get_current_user(access_token)
            if user_info:
                results["get_current_user"] = True
        
        # Test 5: List Accounts
        accounts = test_list_accounts(access_token)
        results["list_accounts"] = True
        
        # Test 6: Create Account (optional)
        account = test_create_account(access_token)
        if account:
            results["create_account"] = account
            account_id = account.get('account_id')
        else:
            account_id = "default"  # Use default account
        
        # Test 7: Create Strategy
        strategy = test_create_strategy(access_token, account_id)
        if strategy:
            results["create_strategy"] = True
            strategy_id = strategy.get('id')
        else:
            print_error("Cannot continue without strategy creation")
            return False
        
        # Test 8: Database Strategy Verification
        if strategy_id and user_id:
            results["database_strategy_verification"] = test_database_strategy_verification(strategy_id, user_id)
        
        # Test 9: List Strategies
        strategies = test_list_strategies(access_token)
        if strategies is not None:
            results["list_strategies"] = True
        
        # Test 10: Data Persistence
        if strategy_id and access_token:
            results["data_persistence"] = test_data_persistence(access_token, user_id, strategy_id)
        
    except Exception as e:
        print_error(f"Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Print summary
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print("Test Summary")
    print(f"{'='*60}{Colors.RESET}\n")
    
    total_tests = len([k for k in results.keys() if k != "create_account"])
    passed_tests = sum(1 for k, v in results.items() if k != "create_account" and v is True)
    
    for test_name, result in results.items():
        if test_name == "create_account":
            if result:
                print_success(f"{test_name}: Account created")
            else:
                print_warning(f"{test_name}: Skipped (using default account)")
        elif result:
            print_success(f"{test_name}: PASSED")
        else:
            print_error(f"{test_name}: FAILED")
    
    print(f"\n{Colors.BOLD}Results: {passed_tests}/{total_tests} tests passed{Colors.RESET}")
    
    if passed_tests == total_tests:
        print_success("\n✓ All tests passed! End-to-end flow is working correctly.")
        return True
    else:
        print_error(f"\n✗ {total_tests - passed_tests} test(s) failed. Please review the errors above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

