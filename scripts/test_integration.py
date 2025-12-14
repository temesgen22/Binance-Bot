"""
Comprehensive integration test for database + authentication system.
Tests user registration, login, database operations, and role assignment.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import init_database, get_db_session
from app.services.database_service import DatabaseService
from app.core.auth import get_password_hash, verify_password, create_access_token
from app.models.db_models import User, Role, Account
from loguru import logger
from uuid import uuid4

logger.info("=" * 60)
logger.info("Integration Test: Database + Authentication")
logger.info("=" * 60)
logger.info("")

# Initialize database
init_database()

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
                import traceback
                traceback.print_exc()
                return None
        return wrapper
    return decorator

# Test data
test_username = f"testuser_{uuid4().hex[:8]}"
test_email = f"test_{uuid4().hex[:8]}@example.com"
test_password = "TestPassword123!"
test_user_id = None
test_account_id = None

# ============================================
# TEST 1: User Registration via Database Service
# ============================================
@test("User Registration via Database Service")
def test_user_registration():
    global test_user_id
    
    with get_db_session() as db:
        db_service = DatabaseService(db)
        
        # Hash password
        password_hash = get_password_hash(test_password)
        
        # Create user
        user = db_service.create_user(
            username=test_username,
            email=test_email,
            password_hash=password_hash,
            full_name="Test User"
        )
        
        test_user_id = user.id
        assert user.id is not None
        assert user.username == test_username
        assert user.email == test_email
        assert user.is_active is True
        assert user.is_verified is False
        
        return user

# ============================================
# TEST 2: Password Verification
# ============================================
@test("Password Verification")
def test_password_verification():
    with get_db_session() as db:
        db_service = DatabaseService(db)
        user = db_service.get_user_by_username(test_username)
        
        assert user is not None
        assert verify_password(test_password, user.password_hash) is True
        assert verify_password("wrong_password", user.password_hash) is False

# ============================================
# TEST 3: Role Assignment
# ============================================
@test("Role Assignment")
def test_role_assignment():
    with get_db_session() as db:
        from sqlalchemy.orm import Session
        db_service = DatabaseService(db)
        user = db_service.get_user_by_id(test_user_id)
        
        # Get "user" role
        user_role = db.query(Role).filter(Role.name == "user").first()
        assert user_role is not None, "Default 'user' role should exist"
        
        # Assign role
        user.roles.append(user_role)
        db.commit()
        db.refresh(user)
        
        assert len(user.roles) > 0
        assert any(role.name == "user" for role in user.roles)

# ============================================
# TEST 4: JWT Token Creation
# ============================================
@test("JWT Token Creation")
def test_jwt_token_creation():
    token_data = {
        "sub": str(test_user_id),
        "username": test_username,
        "email": test_email
    }
    
    access_token = create_access_token(token_data)
    assert access_token is not None
    assert len(access_token) > 0
    
    # Verify token can be decoded
    from app.core.auth import decode_token
    payload = decode_token(access_token)
    assert payload is not None
    assert payload.get("sub") == str(test_user_id)
    assert payload.get("username") == test_username

# ============================================
# TEST 5: Account Creation
# ============================================
@test("Account Creation")
def test_account_creation():
    global test_account_id
    
    with get_db_session() as db:
        db_service = DatabaseService(db)
        
        account = db_service.create_account(
            user_id=test_user_id,
            account_id="test_account_1",
            api_key_encrypted="encrypted_key_123",
            api_secret_encrypted="encrypted_secret_456",
            name="Test Account",
            testnet=True,
            is_default=True
        )
        
        test_account_id = account.id
        assert account.id is not None
        assert account.user_id == test_user_id
        assert account.account_id == "test_account_1"
        assert account.is_default is True

# ============================================
# TEST 6: Strategy Creation
# ============================================
@test("Strategy Creation")
def test_strategy_creation():
    with get_db_session() as db:
        db_service = DatabaseService(db)
        
        strategy = db_service.create_strategy(
            user_id=test_user_id,
            strategy_id=f"test_strategy_{uuid4().hex[:8]}",
            name="Test Strategy",
            symbol="BTCUSDT",
            strategy_type="scalping",
            account_id=test_account_id,
            leverage=5,
            risk_per_trade=0.01,
            params={"ema_fast": 8, "ema_slow": 21}
        )
        
        assert strategy.id is not None
        assert strategy.user_id == test_user_id
        assert strategy.strategy_id is not None
        assert strategy.leverage == 5
        assert strategy.risk_per_trade == 0.01

# ============================================
# TEST 7: User Queries
# ============================================
@test("User Queries")
def test_user_queries():
    with get_db_session() as db:
        db_service = DatabaseService(db)
        
        # Get by username
        user_by_username = db_service.get_user_by_username(test_username)
        assert user_by_username is not None
        assert user_by_username.id == test_user_id
        
        # Get by email
        user_by_email = db_service.get_user_by_email(test_email)
        assert user_by_email is not None
        assert user_by_email.id == test_user_id
        
        # Get by ID
        user_by_id = db_service.get_user_by_id(test_user_id)
        assert user_by_id is not None
        assert user_by_id.username == test_username

# ============================================
# TEST 8: Account Queries
# ============================================
@test("Account Queries")
def test_account_queries():
    with get_db_session() as db:
        db_service = DatabaseService(db)
        
        # Get user accounts
        accounts = db_service.get_user_accounts(test_user_id)
        assert len(accounts) > 0
        assert any(acc.account_id == "test_account_1" for acc in accounts)
        
        # Get default account
        default_account = db_service.get_default_account(test_user_id)
        assert default_account is not None
        assert default_account.is_default is True

# ============================================
# TEST 9: Strategy Queries
# ============================================
@test("Strategy Queries")
def test_strategy_queries():
    with get_db_session() as db:
        db_service = DatabaseService(db)
        
        # Get user strategies
        strategies = db_service.get_user_strategies(test_user_id)
        assert len(strategies) > 0
        assert any(s.symbol == "BTCUSDT" for s in strategies)

# ============================================
# TEST 10: Data Isolation (Multi-User)
# ============================================
@test("Data Isolation (Multi-User)")
def test_data_isolation():
    with get_db_session() as db:
        db_service = DatabaseService(db)
        
        # Create second user
        user2 = db_service.create_user(
            username=f"testuser2_{uuid4().hex[:8]}",
            email=f"test2_{uuid4().hex[:8]}@example.com",
            password_hash=get_password_hash("Password123!"),
            full_name="Test User 2"
        )
        
        # Create account for user2
        account2 = db_service.create_account(
            user_id=user2.id,
            account_id="test_account_2",
            api_key_encrypted="encrypted_key_789",
            api_secret_encrypted="encrypted_secret_012",
            name="Test Account 2",
            testnet=True
        )
        
        # Create strategy for user2
        strategy2 = db_service.create_strategy(
            user_id=user2.id,
            strategy_id=f"test_strategy2_{uuid4().hex[:8]}",
            name="Test Strategy 2",
            symbol="ETHUSDT",
            strategy_type="scalping",
            account_id=account2.id,
            leverage=10,
            risk_per_trade=0.02,
            params={"ema_fast": 5, "ema_slow": 20}
        )
        
        # Verify isolation: user1 should not see user2's data
        user1_strategies = db_service.get_user_strategies(test_user_id)
        user2_strategies = db_service.get_user_strategies(user2.id)
        
        assert len(user1_strategies) > 0
        assert len(user2_strategies) > 0
        assert all(s.user_id == test_user_id for s in user1_strategies)
        assert all(s.user_id == user2.id for s in user2_strategies)
        assert not any(s.id == strategy2.id for s in user1_strategies)

# ============================================
# RUN ALL TESTS
# ============================================
logger.info("Running integration tests...")
logger.info("")

test_user_registration()
test_password_verification()
test_role_assignment()
test_jwt_token_creation()
test_account_creation()
test_strategy_creation()
test_user_queries()
test_account_queries()
test_strategy_queries()
test_data_isolation()

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
    logger.info("🎉 All integration tests passed!")
    logger.info("")
    logger.info("Database + Authentication integration is working correctly!")
    logger.info("Ready to proceed with Phase 3: StrategyService integration")
else:
    logger.error("⚠ Some tests failed. Please review the errors above.")
    sys.exit(1)

logger.info("=" * 60)

