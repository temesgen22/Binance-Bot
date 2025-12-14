"""
Comprehensive test script for database setup.
Tests connection, migrations, and basic CRUD operations.
"""
import sys
from pathlib import Path
from datetime import datetime
from uuid import uuid4

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import (
    init_database, get_db_session, get_engine, 
    create_tables, close_database
)
from app.models.db_models import (
    User, Role, Account, Strategy, Trade, TradePair,
    Backtest, BacktestTrade, StrategyMetric, SystemEvent,
    UserSession, APIToken
)
from app.core.config import get_settings
from loguru import logger
from sqlalchemy import inspect, text


def test_connection():
    """Test 1: Database connection."""
    logger.info("=" * 60)
    logger.info("TEST 1: Database Connection")
    logger.info("=" * 60)
    
    try:
        settings = get_settings()
        logger.info(f"Database URL: {settings.database_url.split('@')[-1] if '@' in settings.database_url else '***'}")
        
        init_database()
        logger.info("✓ Database initialized successfully")
        
        # Test raw connection
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            logger.info(f"✓ PostgreSQL version: {version.split(',')[0]}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Connection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tables_exist():
    """Test 2: Check if tables exist."""
    logger.info("=" * 60)
    logger.info("TEST 2: Table Existence Check")
    logger.info("=" * 60)
    
    try:
        engine = get_engine()
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        expected_tables = [
            'users', 'roles', 'user_roles',
            'accounts', 'strategies', 'trades', 'trade_pairs',
            'backtests', 'backtest_trades', 'strategy_metrics',
            'system_events', 'user_sessions', 'api_tokens'
        ]
        
        logger.info(f"Found {len(existing_tables)} tables in database")
        
        missing_tables = []
        for table in expected_tables:
            if table in existing_tables:
                logger.info(f"✓ Table '{table}' exists")
            else:
                logger.warning(f"✗ Table '{table}' missing")
                missing_tables.append(table)
        
        if missing_tables:
            logger.warning(f"Missing tables: {missing_tables}")
            logger.info("Run 'alembic upgrade head' to create tables")
            return False
        
        logger.info("✓ All expected tables exist")
        return True
    except Exception as e:
        logger.error(f"✗ Table check failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_crud_operations():
    """Test 3: Basic CRUD operations."""
    logger.info("=" * 60)
    logger.info("TEST 3: CRUD Operations")
    logger.info("=" * 60)
    
    try:
        with get_db_session() as db:
            # Test User creation
            logger.info("Testing User creation...")
            test_user = User(
                username=f"test_user_{uuid4().hex[:8]}",
                email=f"test_{uuid4().hex[:8]}@example.com",
                password_hash="test_hash",
                full_name="Test User",
                is_active=True,
                is_verified=True
            )
            db.add(test_user)
            db.flush()  # Get the ID without committing
            logger.info(f"✓ Created test user: {test_user.username} (ID: {test_user.id})")
            
            # Test Role creation
            logger.info("Testing Role creation...")
            test_role = Role(
                name=f"test_role_{uuid4().hex[:8]}",
                description="Test role",
                is_system=False,
                permissions={"read": True, "write": False}
            )
            db.add(test_role)
            db.flush()
            logger.info(f"✓ Created test role: {test_role.name} (ID: {test_role.id})")
            
            # Test Account creation
            logger.info("Testing Account creation...")
            test_account = Account(
                user_id=test_user.id,
                account_id=f"test_account_{uuid4().hex[:8]}",
                api_key_encrypted="encrypted_key",
                api_secret_encrypted="encrypted_secret",
                testnet=True,
                is_active=True,
                is_default=True
            )
            db.add(test_account)
            db.flush()
            logger.info(f"✓ Created test account: {test_account.account_id} (ID: {test_account.id})")
            
            # Test Strategy creation
            logger.info("Testing Strategy creation...")
            test_strategy = Strategy(
                user_id=test_user.id,
                account_id=test_account.id,
                strategy_id=f"test_strategy_{uuid4().hex[:8]}",
                name="Test Strategy",
                strategy_type="scalping",
                symbol="BTCUSDT",
                leverage=5,
                risk_per_trade=0.01,
                params={"param1": "value1"},
                meta={"meta1": "value1"}
            )
            db.add(test_strategy)
            db.flush()
            logger.info(f"✓ Created test strategy: {test_strategy.strategy_id} (ID: {test_strategy.id})")
            
            # Test Trade creation
            logger.info("Testing Trade creation...")
            test_trade = Trade(
                user_id=test_user.id,
                strategy_id=test_strategy.id,
                order_id=1234567890123456789,  # BigInteger
                symbol="BTCUSDT",
                side="BUY",
                order_type="MARKET",
                executed_qty=0.001,
                price=50000.0,
                status="FILLED",
                timestamp=datetime.utcnow()
            )
            db.add(test_trade)
            db.flush()
            logger.info(f"✓ Created test trade: Order ID {test_trade.order_id} (ID: {test_trade.id})")
            
            # Test READ operations
            logger.info("Testing READ operations...")
            user_read = db.query(User).filter(User.id == test_user.id).first()
            assert user_read is not None, "User not found after creation"
            logger.info(f"✓ Read user: {user_read.username}")
            
            role_read = db.query(Role).filter(Role.id == test_role.id).first()
            assert role_read is not None, "Role not found after creation"
            logger.info(f"✓ Read role: {role_read.name}")
            
            account_read = db.query(Account).filter(Account.id == test_account.id).first()
            assert account_read is not None, "Account not found after creation"
            logger.info(f"✓ Read account: {account_read.account_id}")
            
            strategy_read = db.query(Strategy).filter(Strategy.id == test_strategy.id).first()
            assert strategy_read is not None, "Strategy not found after creation"
            logger.info(f"✓ Read strategy: {strategy_read.strategy_id}")
            
            trade_read = db.query(Trade).filter(Trade.id == test_trade.id).first()
            assert trade_read is not None, "Trade not found after creation"
            logger.info(f"✓ Read trade: Order ID {trade_read.order_id}")
            
            # Test UPDATE operations
            logger.info("Testing UPDATE operations...")
            user_read.full_name = "Updated Test User"
            db.flush()
            logger.info(f"✓ Updated user: {user_read.full_name}")
            
            strategy_read.name = "Updated Test Strategy"
            db.flush()
            logger.info(f"✓ Updated strategy: {strategy_read.name}")
            
            # Test DELETE operations (cleanup)
            logger.info("Testing DELETE operations (cleanup)...")
            db.delete(test_trade)
            db.delete(test_strategy)
            db.delete(test_account)
            db.delete(test_role)
            db.delete(test_user)
            db.commit()
            logger.info("✓ Deleted all test records")
            
        logger.info("✓ All CRUD operations passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ CRUD test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_constraints():
    """Test 4: Database constraints."""
    logger.info("=" * 60)
    logger.info("TEST 4: Database Constraints")
    logger.info("=" * 60)
    
    try:
        with get_db_session() as db:
            # Test unique username constraint
            logger.info("Testing unique username constraint...")
            test_user1 = User(
                username="unique_test_user",
                email="unique1@example.com",
                password_hash="hash1"
            )
            db.add(test_user1)
            db.commit()
            
            test_user2 = User(
                username="unique_test_user",  # Duplicate username
                email="unique2@example.com",
                password_hash="hash2"
            )
            db.add(test_user2)
            
            try:
                db.commit()
                logger.error("✗ Unique username constraint failed (should have raised error)")
                db.delete(test_user2)
                db.delete(test_user1)
                db.commit()
                return False
            except Exception as e:
                db.rollback()
                logger.info(f"✓ Unique username constraint works: {type(e).__name__}")
                db.delete(test_user1)
                db.commit()
            
            # Test unique email constraint
            logger.info("Testing unique email constraint...")
            test_user3 = User(
                username="test_user_3",
                email="unique_email@example.com",
                password_hash="hash3"
            )
            db.add(test_user3)
            db.commit()
            
            test_user4 = User(
                username="test_user_4",
                email="unique_email@example.com",  # Duplicate email
                password_hash="hash4"
            )
            db.add(test_user4)
            
            try:
                db.commit()
                logger.error("✗ Unique email constraint failed (should have raised error)")
                db.delete(test_user4)
                db.delete(test_user3)
                db.commit()
                return False
            except Exception as e:
                db.rollback()
                logger.info(f"✓ Unique email constraint works: {type(e).__name__}")
                db.delete(test_user3)
                db.commit()
            
        logger.info("✓ All constraint tests passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ Constraint test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_relationships():
    """Test 5: Database relationships."""
    logger.info("=" * 60)
    logger.info("TEST 5: Database Relationships")
    logger.info("=" * 60)
    
    try:
        with get_db_session() as db:
            # Create user
            test_user = User(
                username=f"rel_test_user_{uuid4().hex[:8]}",
                email=f"rel_test_{uuid4().hex[:8]}@example.com",
                password_hash="hash"
            )
            db.add(test_user)
            db.flush()
            
            # Create role
            test_role = Role(
                name=f"rel_test_role_{uuid4().hex[:8]}",
                permissions={"read": True}
            )
            db.add(test_role)
            db.flush()
            
            # Test user-role relationship
            logger.info("Testing user-role relationship...")
            test_user.roles.append(test_role)
            db.flush()
            logger.info(f"✓ User has {len(test_user.roles)} role(s)")
            logger.info(f"✓ Role has {len(test_role.users)} user(s)")
            
            # Test user-account relationship
            logger.info("Testing user-account relationship...")
            test_account = Account(
                user_id=test_user.id,
                account_id=f"rel_account_{uuid4().hex[:8]}",
                api_key_encrypted="key",
                api_secret_encrypted="secret"
            )
            db.add(test_account)
            db.flush()
            logger.info(f"✓ User has {len(test_user.accounts)} account(s)")
            assert test_account.user_id == test_user.id, "Account user_id mismatch"
            
            # Test user-strategy relationship
            logger.info("Testing user-strategy relationship...")
            test_strategy = Strategy(
                user_id=test_user.id,
                account_id=test_account.id,
                strategy_id=f"rel_strategy_{uuid4().hex[:8]}",
                name="Rel Test Strategy",
                strategy_type="scalping",
                symbol="BTCUSDT",
                leverage=5,
                risk_per_trade=0.01
            )
            db.add(test_strategy)
            db.flush()
            logger.info(f"✓ User has {len(test_user.strategies)} strategy(ies)")
            assert test_strategy.user_id == test_user.id, "Strategy user_id mismatch"
            
            # Cleanup
            db.delete(test_strategy)
            db.delete(test_account)
            db.delete(test_user)
            db.delete(test_role)
            db.commit()
            
        logger.info("✓ All relationship tests passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ Relationship test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    logger.info("Starting comprehensive database setup tests...")
    logger.info("")
    
    results = []
    
    # Test 1: Connection
    results.append(("Connection", test_connection()))
    logger.info("")
    
    # Test 2: Tables exist
    results.append(("Tables Exist", test_tables_exist()))
    logger.info("")
    
    # Test 3: CRUD operations (only if tables exist)
    if results[-1][1]:
        results.append(("CRUD Operations", test_crud_operations()))
        logger.info("")
        
        # Test 4: Constraints
        results.append(("Constraints", test_constraints()))
        logger.info("")
        
        # Test 5: Relationships
        results.append(("Relationships", test_relationships()))
        logger.info("")
    else:
        logger.warning("Skipping CRUD, Constraints, and Relationships tests (tables don't exist)")
        logger.info("Run 'alembic revision --autogenerate -m \"Initial schema\"' to create migration")
        logger.info("Then run 'alembic upgrade head' to apply migration")
    
    # Summary
    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        logger.info(f"{test_name}: {status}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        logger.info("")
        logger.info("🎉 All tests passed!")
    else:
        logger.info("")
        logger.warning("⚠ Some tests failed. Check the logs above for details.")
    
    close_database()
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

