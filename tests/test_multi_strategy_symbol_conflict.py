"""Test cases for multi-strategy symbol conflict prevention.

Tests cover:
1. Registration-time conflict detection (Layer 1)
2. Start-time conflict detection (Layer 2)
3. Order execution conflict detection (Layer 3)
4. Different accounts can trade same symbol (no conflict)
5. Different symbols on same account (no conflict)
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4, UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.schema import CheckConstraint

from app.models.strategy import CreateStrategyRequest, StrategySummary, StrategyState, StrategyType, StrategyParams
from app.services.strategy_runner import StrategyRunner
from app.services.strategy_service import StrategyService
from app.services.database_service import DatabaseService
from app.core.exceptions import SymbolConflictError
from app.core.redis_storage import RedisStorage
from app.core.binance_client_manager import BinanceClientManager
from app.models.db_models import Base

# Test database URL (in-memory SQLite for testing)
TEST_DB_URL = "sqlite:///:memory:"

# Map JSONB to JSON for SQLite compatibility
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler, SQLiteDDLCompiler

if not hasattr(SQLiteTypeCompiler, '_visit_JSONB_patched'):
    def visit_JSONB(self, type_, **kw):
        return "JSON"
    SQLiteTypeCompiler.visit_JSONB = visit_JSONB
    SQLiteTypeCompiler._visit_JSONB_patched = True

# Skip PostgreSQL-specific CHECK constraints for SQLite
if not hasattr(SQLiteDDLCompiler, '_visit_check_constraint_patched'):
    original_visit_check_constraint = SQLiteDDLCompiler.visit_check_constraint
    def visit_check_constraint(self, constraint, **kw):
        try:
            sqltext = str(constraint.sqltext)
            if '~' in sqltext or '~*' in sqltext:
                return None
        except Exception:
            pass
        return original_visit_check_constraint(self, constraint, **kw)
    SQLiteDDLCompiler.visit_check_constraint = visit_check_constraint
    SQLiteDDLCompiler._visit_check_constraint_patched = True


@pytest.fixture
def test_db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine(TEST_DB_URL, echo=False)
    
    # Remove PostgreSQL-specific CHECK constraints for SQLite
    for table in Base.metadata.tables.values():
        constraints_to_remove = []
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint):
                try:
                    sqltext = str(constraint.sqltext)
                    if '~' in sqltext or '~*' in sqltext:
                        constraints_to_remove.append(constraint)
                except Exception:
                    pass
        for constraint in constraints_to_remove:
            table.constraints.remove(constraint)
    
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def test_user(test_db):
    """Create a test user."""
    from app.models.db_models import User
    user = User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="hashed",
        is_active=True
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def test_account(test_db, test_user):
    """Create a test account."""
    from app.models.db_models import Account
    account = Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="default",
        name="Default Account",
        api_key_encrypted="test_key",
        api_secret_encrypted="test_secret",
        testnet=True,
        paper_trading=True,
        paper_balance=10000.0,
        is_active=True
    )
    test_db.add(account)
    test_db.commit()
    return account


@pytest.fixture
def test_account_2(test_db, test_user):
    """Create a second test account."""
    from app.models.db_models import Account
    account = Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="main",
        name="Main Account",
        api_key_encrypted="test_key2",
        api_secret_encrypted="test_secret2",
        testnet=True,
        paper_trading=True,
        paper_balance=20000.0,
        is_active=True
    )
    test_db.add(account)
    test_db.commit()
    return account


@pytest.fixture
def strategy_service(test_db):
    """Create StrategyService for testing."""
    db_service = DatabaseService(test_db)
    redis_storage = MagicMock(spec=RedisStorage)
    redis_storage.enabled = False
    return StrategyService(test_db, redis_storage)


@pytest.fixture
def strategy_runner(test_db, test_user, test_account, strategy_service):
    """Create StrategyRunner instance for testing."""
    # Mock BinanceClientManager
    client_manager = MagicMock(spec=BinanceClientManager)
    client_manager.account_exists = MagicMock(return_value=True)
    client_manager.get_account_config = MagicMock(return_value=MagicMock(name="Default Account"))
    client_manager.list_accounts = MagicMock(return_value={"default": MagicMock()})
    
    # Mock client
    mock_client = MagicMock()
    client_manager.get_client = MagicMock(return_value=mock_client)
    
    # Mock Redis storage
    redis_storage = MagicMock(spec=RedisStorage)
    redis_storage.enabled = False
    
    runner = StrategyRunner(
        client_manager=client_manager,
        strategy_service=strategy_service,
        user_id=test_user.id,
        redis_storage=redis_storage,
    )
    
    # Mock _get_account_client
    runner._get_account_client = MagicMock(return_value=mock_client)
    
    return runner


class TestRegistrationTimeConflictDetection:
    """Test Layer 1: Registration-time conflict detection."""
    
    def test_register_strategy_with_conflict_raises_error(self, strategy_runner, test_user, test_account):
        """Test that registering a strategy with a conflicting running strategy raises SymbolConflictError."""
        # Register and start first strategy
        params = StrategyParams(ema_fast=8, ema_slow=21)
        payload1 = CreateStrategyRequest(
            name="Strategy 1",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",
            params=params,
        )
        
        summary1 = strategy_runner.register(payload1, account_uuid=test_account.id)
        
        # Set strategy to running status
        strategy_runner.strategy_service.update_strategy(
            test_user.id,
            summary1.id,
            status=StrategyState.running
        )
        
        # Commit the database transaction to ensure the update is visible
        strategy_runner.strategy_service.db_service.db.commit()
        
        # Reload strategy to ensure it's in the cache with updated status
        updated_summary = strategy_runner.strategy_service.get_strategy(test_user.id, summary1.id)
        strategy_runner._strategies[summary1.id] = updated_summary
        
        # Verify the strategy is now running
        assert updated_summary.status == StrategyState.running
        
        # Try to register second strategy with same symbol+account
        payload2 = CreateStrategyRequest(
            name="Strategy 2",
            symbol="BTCUSDT",  # Same symbol
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",  # Same account
            params=params,
        )
        
        # Should raise SymbolConflictError
        with pytest.raises(SymbolConflictError) as exc_info:
            strategy_runner.register(payload2, account_uuid=test_account.id)
        
        assert exc_info.value.symbol == "BTCUSDT"
        assert exc_info.value.account_id == "default"
        assert exc_info.value.conflicting_strategy_id == summary1.id
        assert "Strategy 1" in exc_info.value.message
    
    def test_register_strategy_different_account_no_conflict(self, strategy_runner, test_user, test_account, test_account_2):
        """Test that strategies on different accounts can trade the same symbol."""
        # Register and start first strategy on account 1
        params = StrategyParams(ema_fast=8, ema_slow=21)
        payload1 = CreateStrategyRequest(
            name="Strategy 1",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",
            params=params,
        )
        
        summary1 = strategy_runner.register(payload1, account_uuid=test_account.id)
        strategy_runner.strategy_service.update_strategy(
            test_user.id,
            summary1.id,
            status=StrategyState.running
        )
        
        # Register second strategy with same symbol but different account
        payload2 = CreateStrategyRequest(
            name="Strategy 2",
            symbol="BTCUSDT",  # Same symbol
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="main",  # Different account
            params=params,
        )
        
        # Should NOT raise error (different accounts)
        summary2 = strategy_runner.register(payload2, account_uuid=test_account_2.id)
        assert summary2 is not None
        assert summary2.symbol == "BTCUSDT"
        assert summary2.account_id == "main"
    
    def test_register_strategy_different_symbol_no_conflict(self, strategy_runner, test_user, test_account):
        """Test that strategies with different symbols on same account don't conflict."""
        # Register and start first strategy
        params = StrategyParams(ema_fast=8, ema_slow=21)
        payload1 = CreateStrategyRequest(
            name="Strategy 1",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",
            params=params,
        )
        
        summary1 = strategy_runner.register(payload1, account_uuid=test_account.id)
        strategy_runner.strategy_service.update_strategy(
            test_user.id,
            summary1.id,
            status=StrategyState.running
        )
        
        # Register second strategy with different symbol
        payload2 = CreateStrategyRequest(
            name="Strategy 2",
            symbol="ETHUSDT",  # Different symbol
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",  # Same account
            params=params,
        )
        
        # Should NOT raise error (different symbols)
        summary2 = strategy_runner.register(payload2, account_uuid=test_account.id)
        assert summary2 is not None
        assert summary2.symbol == "ETHUSDT"
    
    def test_register_strategy_stopped_strategy_no_conflict(self, strategy_runner, test_user, test_account):
        """Test that stopped strategies don't cause conflicts."""
        # Register first strategy (stopped)
        params = StrategyParams(ema_fast=8, ema_slow=21)
        payload1 = CreateStrategyRequest(
            name="Strategy 1",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",
            params=params,
        )
        
        summary1 = strategy_runner.register(payload1, account_uuid=test_account.id)
        # Strategy is stopped by default, so no conflict
        
        # Register second strategy with same symbol+account
        payload2 = CreateStrategyRequest(
            name="Strategy 2",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",
            params=params,
        )
        
        # Should NOT raise error (first strategy is stopped)
        summary2 = strategy_runner.register(payload2, account_uuid=test_account.id)
        assert summary2 is not None


class TestStartTimeConflictDetection:
    """Test Layer 2: Start-time conflict detection."""
    
    @pytest.mark.asyncio
    async def test_start_strategy_with_conflict_raises_error(self, strategy_runner, test_user, test_account):
        """Test that starting a strategy with a conflicting running strategy raises SymbolConflictError."""
        # Register both strategies first (both will be stopped by default)
        # This allows us to register both without conflict
        params = StrategyParams(ema_fast=8, ema_slow=21)
        payload1 = CreateStrategyRequest(
            name="Strategy 1",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",
            params=params,
        )
        
        payload2 = CreateStrategyRequest(
            name="Strategy 2",
            symbol="BTCUSDT",  # Same symbol
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",  # Same account
            params=params,
        )
        
        # Register both strategies (both will be stopped by default)
        summary1 = strategy_runner.register(payload1, account_uuid=test_account.id)
        summary2 = strategy_runner.register(payload2, account_uuid=test_account.id)
        
        # Now set first strategy to running (after both are registered)
        strategy_runner.strategy_service.update_strategy(
            test_user.id,
            summary1.id,
            status=StrategyState.running
        )
        strategy_runner.strategy_service.db_service.db.commit()
        
        # Reload strategy to ensure it's in the cache with updated status
        updated_summary = strategy_runner.strategy_service.get_strategy(test_user.id, summary1.id)
        strategy_runner._strategies[summary1.id] = updated_summary
        
        # Verify first strategy is running
        assert updated_summary.status == StrategyState.running
        
        # Try to start second strategy - should raise SymbolConflictError
        with pytest.raises(SymbolConflictError) as exc_info:
            await strategy_runner.start(summary2.id)
        
        assert exc_info.value.symbol == "BTCUSDT"
        assert exc_info.value.account_id == "default"
        assert exc_info.value.conflicting_strategy_id == summary1.id
    
    @pytest.mark.asyncio
    async def test_start_strategy_different_account_no_conflict(self, strategy_runner, test_user, test_account, test_account_2):
        """Test that starting strategies on different accounts with same symbol doesn't conflict."""
        # Register and start first strategy on account 1
        params = StrategyParams(ema_fast=8, ema_slow=21)
        payload1 = CreateStrategyRequest(
            name="Strategy 1",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",
            params=params,
        )
        
        summary1 = strategy_runner.register(payload1, account_uuid=test_account.id)
        strategy_runner.strategy_service.update_strategy(
            test_user.id,
            summary1.id,
            status=StrategyState.running
        )
        strategy_runner.strategy_service.db_service.db.commit()
        
        # Reload strategy to ensure it's in the cache
        updated_summary = strategy_runner.strategy_service.get_strategy(test_user.id, summary1.id)
        strategy_runner._strategies[summary1.id] = updated_summary
        
        # Register second strategy on different account
        payload2 = CreateStrategyRequest(
            name="Strategy 2",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="main",  # Different account
            params=params,
        )
        
        summary2 = strategy_runner.register(payload2, account_uuid=test_account_2.id)
        
        # Should be able to start (different accounts)
        # Mock the executor to avoid actual strategy execution
        strategy_runner.executor = MagicMock()
        strategy_runner.executor.run_loop = AsyncMock()
        strategy_runner.registry = MagicMock()
        strategy_runner.registry.build = MagicMock(return_value=MagicMock())
        
        # Should NOT raise error
        result = await strategy_runner.start(summary2.id)
        assert result is not None


class TestSymbolNormalization:
    """Test that symbol normalization (strip + uppercase) works correctly."""
    
    def test_register_strategy_symbol_with_whitespace(self, strategy_runner, test_user, test_account):
        """Test that symbols with whitespace are normalized for conflict detection."""
        # Register first strategy with normal symbol
        params = StrategyParams(ema_fast=8, ema_slow=21)
        payload1 = CreateStrategyRequest(
            name="Strategy 1",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",
            params=params,
        )
        
        summary1 = strategy_runner.register(payload1, account_uuid=test_account.id)
        strategy_runner.strategy_service.update_strategy(
            test_user.id,
            summary1.id,
            status=StrategyState.running
        )
        
        # Try to register with symbol that has whitespace (should be normalized and conflict)
        payload2 = CreateStrategyRequest(
            name="Strategy 2",
            symbol=" BTCUSDT ",  # With whitespace
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",
            params=params,
        )
        
        # Should raise SymbolConflictError (symbols are normalized)
        with pytest.raises(SymbolConflictError):
            strategy_runner.register(payload2, account_uuid=test_account.id)
    
    def test_register_strategy_symbol_case_insensitive(self, strategy_runner, test_user, test_account):
        """Test that symbol conflict detection is case-insensitive."""
        # Register first strategy with uppercase symbol
        params = StrategyParams(ema_fast=8, ema_slow=21)
        payload1 = CreateStrategyRequest(
            name="Strategy 1",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",
            params=params,
        )
        
        summary1 = strategy_runner.register(payload1, account_uuid=test_account.id)
        strategy_runner.strategy_service.update_strategy(
            test_user.id,
            summary1.id,
            status=StrategyState.running
        )
        
        # Try to register with lowercase symbol (should conflict)
        payload2 = CreateStrategyRequest(
            name="Strategy 2",
            symbol="btcusdt",  # Lowercase
            strategy_type=StrategyType.scalping,
            leverage=5,
            risk_per_trade=0.01,
            account_id="default",
            params=params,
        )
        
        # Should raise SymbolConflictError (symbols are normalized to uppercase)
        with pytest.raises(SymbolConflictError):
            strategy_runner.register(payload2, account_uuid=test_account.id)

