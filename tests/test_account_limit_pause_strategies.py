"""Test case for pausing all strategies for a specific account when daily/weekly limits are exceeded.

Tests verify that:
1. When daily/weekly limit is exceeded, all strategies for that account are paused
2. Strategies from other accounts are NOT affected (remain running)
3. Status is correctly set to "stopped_by_risk"
4. Account-level enforcement events are logged
5. Only the affected account's strategies are paused
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.schema import CheckConstraint

from app.models.db_models import Strategy, User, Account, SystemEvent, Base
from app.models.strategy import StrategyState
from app.services.strategy_runner import StrategyRunner
from app.services.strategy_order_manager import StrategyOrderManager
from app.services.strategy_service import StrategyService
from app.services.database_service import DatabaseService
from app.core.redis_storage import RedisStorage
from app.core.binance_client_manager import BinanceClientManager
from app.core.config import get_settings

# Test database URL (in-memory SQLite for testing)
TEST_DB_URL = "sqlite:///:memory:"

# Map JSONB to JSON for SQLite compatibility
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler, SQLiteDDLCompiler

if not hasattr(SQLiteTypeCompiler, '_visit_JSONB_patched'):
    def visit_JSONB(self, type_, **kw):
        """Map JSONB to JSON for SQLite compatibility."""
        return "JSON"
    
    SQLiteTypeCompiler.visit_JSONB = visit_JSONB
    SQLiteTypeCompiler._visit_JSONB_patched = True

# Skip PostgreSQL-specific CHECK constraints for SQLite
if not hasattr(SQLiteDDLCompiler, '_visit_check_constraint_patched'):
    original_visit_check_constraint = SQLiteDDLCompiler.visit_check_constraint
    
    def visit_check_constraint(self, constraint, **kw):
        """Skip CHECK constraints with PostgreSQL regex operators for SQLite."""
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
    """Create test user."""
    user = User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
        is_active=True
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def test_account_1(test_db, test_user):
    """Create first test account."""
    account = Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="account1",
        name="Test Account 1",
        api_key_encrypted="test_api_key_1",
        api_secret_encrypted="test_api_secret_1",
        testnet=True,
        is_active=True,
        is_default=False
    )
    test_db.add(account)
    test_db.commit()
    return account


@pytest.fixture
def test_account_2(test_db, test_user):
    """Create second test account."""
    account = Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="account2",
        name="Test Account 2",
        api_key_encrypted="test_api_key_2",
        api_secret_encrypted="test_api_secret_2",
        testnet=True,
        is_active=True,
        is_default=False
    )
    test_db.add(account)
    test_db.commit()
    return account


@pytest.fixture
def test_strategies_account_1(test_db, test_user, test_account_1):
    """Create multiple strategies for account 1."""
    strategies = []
    for i in range(3):
        strategy = Strategy(
            id=uuid4(),
            user_id=test_user.id,
            account_id=test_account_1.id,
            strategy_id=f"strategy-account1-{i+1}",
            name=f"Strategy Account1 {i+1}",
            symbol="BTCUSDT",
            strategy_type="scalping",
            leverage=5,
            risk_per_trade=Decimal("0.01"),
            fixed_amount=Decimal("1000.0"),
            max_positions=1,
            params={},
            status="running"  # All running
        )
        test_db.add(strategy)
        strategies.append(strategy)
    test_db.commit()
    return strategies


@pytest.fixture
def test_strategies_account_2(test_db, test_user, test_account_2):
    """Create multiple strategies for account 2."""
    strategies = []
    for i in range(2):
        strategy = Strategy(
            id=uuid4(),
            user_id=test_user.id,
            account_id=test_account_2.id,
            strategy_id=f"strategy-account2-{i+1}",
            name=f"Strategy Account2 {i+1}",
            symbol="ETHUSDT",
            strategy_type="scalping",
            leverage=5,
            risk_per_trade=Decimal("0.01"),
            fixed_amount=Decimal("1000.0"),
            max_positions=1,
            params={},
            status="running"  # All running
        )
        test_db.add(strategy)
        strategies.append(strategy)
    test_db.commit()
    return strategies


@pytest.fixture
def strategy_runner(test_db, test_user):
    """Create StrategyRunner instance for testing."""
    db_service = DatabaseService(test_db)
    strategy_service = StrategyService(test_db)
    
    # Mock Redis storage
    redis_storage = MagicMock(spec=RedisStorage)
    redis_storage.enabled = False
    
    # Mock BinanceClientManager
    client_manager = MagicMock(spec=BinanceClientManager)
    
    runner = StrategyRunner(
        client_manager=client_manager,
        strategy_service=strategy_service,
        user_id=test_user.id,
        redis_storage=redis_storage,
    )
    
    return runner


class TestAccountLimitPauseStrategies:
    """Test that pausing strategies works correctly for specific accounts."""
    
    @pytest.mark.asyncio
    async def test_pause_all_strategies_for_account_when_daily_limit_exceeded(
        self,
        test_db,
        test_user,
        test_account_1,
        test_account_2,
        test_strategies_account_1,
        test_strategies_account_2,
        strategy_runner
    ):
        """Test that when daily limit is exceeded, only strategies for that account are paused."""
        
        # Verify initial state: all strategies are running
        account1_strategies = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_1.id,
            Strategy.status == "running"
        ).all()
        assert len(account1_strategies) == 3, "Account 1 should have 3 running strategies"
        
        account2_strategies = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_2.id,
            Strategy.status == "running"
        ).all()
        assert len(account2_strategies) == 2, "Account 2 should have 2 running strategies"
        
        # Simulate daily limit exceeded for account 1
        paused_strategies = await strategy_runner.pause_all_strategies_for_account(
            account_id="account1",
            reason="Daily loss limit exceeded: -$150.00 >= -$100.00"
        )
        
        # Verify account 1 strategies are paused
        assert len(paused_strategies) == 3, "Should pause 3 strategies for account 1"
        assert "strategy-account1-1" in paused_strategies
        assert "strategy-account1-2" in paused_strategies
        assert "strategy-account1-3" in paused_strategies
        
        # Verify account 1 strategies status is "stopped_by_risk"
        account1_strategies_after = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_1.id
        ).all()
        for strategy in account1_strategies_after:
            assert strategy.status == "stopped_by_risk", \
                f"Strategy {strategy.strategy_id} should be stopped_by_risk, got {strategy.status}"
        
        # Verify account 2 strategies are NOT affected (still running)
        account2_strategies_after = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_2.id
        ).all()
        for strategy in account2_strategies_after:
            assert strategy.status == "running", \
                f"Strategy {strategy.strategy_id} should still be running, got {strategy.status}"
        
        # Verify account-level enforcement event was logged
        events = test_db.query(SystemEvent).filter(
            SystemEvent.event_type == "ACCOUNT_STRATEGIES_PAUSED",
            SystemEvent.account_id == test_account_1.id
        ).all()
        
        assert len(events) == 1, "Should have one ACCOUNT_STRATEGIES_PAUSED event"
        event = events[0]
        assert event.event_level == "WARNING"
        assert event.strategy_id is None, "Account-level event should have NULL strategy_id"
        assert "account1" in event.message.lower()
        assert "3" in event.message or "three" in event.message.lower()
        
        # Verify event metadata
        assert event.event_metadata is not None
        assert event.event_metadata.get("account_id") == "account1"
        assert event.event_metadata.get("paused_count") == 3
        assert len(event.event_metadata.get("paused_strategies", [])) == 3
    
    @pytest.mark.asyncio
    async def test_pause_all_strategies_for_account_when_weekly_limit_exceeded(
        self,
        test_db,
        test_user,
        test_account_1,
        test_account_2,
        test_strategies_account_1,
        test_strategies_account_2,
        strategy_runner
    ):
        """Test that when weekly limit is exceeded, only strategies for that account are paused."""
        
        # Simulate weekly limit exceeded for account 2
        paused_strategies = await strategy_runner.pause_all_strategies_for_account(
            account_id="account2",
            reason="Weekly loss limit exceeded: -$500.00 >= -$400.00"
        )
        
        # Verify account 2 strategies are paused
        assert len(paused_strategies) == 2, "Should pause 2 strategies for account 2"
        assert "strategy-account2-1" in paused_strategies
        assert "strategy-account2-2" in paused_strategies
        
        # Verify account 2 strategies status is "stopped_by_risk"
        account2_strategies_after = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_2.id
        ).all()
        for strategy in account2_strategies_after:
            assert strategy.status == "stopped_by_risk", \
                f"Strategy {strategy.strategy_id} should be stopped_by_risk"
        
        # Verify account 1 strategies are NOT affected (still running)
        account1_strategies_after = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_1.id
        ).all()
        for strategy in account1_strategies_after:
            assert strategy.status == "running", \
                f"Strategy {strategy.strategy_id} should still be running"
        
        # Verify account-level enforcement event was logged for account 2
        events = test_db.query(SystemEvent).filter(
            SystemEvent.event_type == "ACCOUNT_STRATEGIES_PAUSED",
            SystemEvent.account_id == test_account_2.id
        ).all()
        
        assert len(events) == 1, "Should have one ACCOUNT_STRATEGIES_PAUSED event for account 2"
        event = events[0]
        assert "account2" in event.message.lower()
        assert "2" in event.message or "two" in event.message.lower()
    
    @pytest.mark.asyncio
    async def test_pause_only_affects_specific_account(
        self,
        test_db,
        test_user,
        test_account_1,
        test_account_2,
        test_strategies_account_1,
        test_strategies_account_2,
        strategy_runner
    ):
        """Test that pausing one account does not affect other accounts."""
        
        # Pause account 1
        paused_account1 = await strategy_runner.pause_all_strategies_for_account(
            account_id="account1",
            reason="Daily loss limit exceeded"
        )
        
        assert len(paused_account1) == 3, "Account 1 should have 3 strategies paused"
        
        # Verify account 1 is paused
        account1_running = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_1.id,
            Strategy.status == "running"
        ).count()
        assert account1_running == 0, "Account 1 should have no running strategies"
        
        account1_paused = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_1.id,
            Strategy.status == "stopped_by_risk"
        ).count()
        assert account1_paused == 3, "Account 1 should have 3 paused strategies"
        
        # Verify account 2 is still running
        account2_running = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_2.id,
            Strategy.status == "running"
        ).count()
        assert account2_running == 2, "Account 2 should still have 2 running strategies"
        
        account2_paused = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_2.id,
            Strategy.status == "stopped_by_risk"
        ).count()
        assert account2_paused == 0, "Account 2 should have no paused strategies"
    
    @pytest.mark.asyncio
    async def test_pause_handles_no_running_strategies(
        self,
        test_db,
        test_user,
        test_account_1,
        strategy_runner
    ):
        """Test that pausing works correctly when account has no running strategies."""
        
        # Create a stopped strategy
        stopped_strategy = Strategy(
            id=uuid4(),
            user_id=test_user.id,
            account_id=test_account_1.id,
            strategy_id="stopped-strategy",
            name="Stopped Strategy",
            symbol="BTCUSDT",
            strategy_type="scalping",
            leverage=5,
            risk_per_trade=Decimal("0.01"),
            fixed_amount=Decimal("1000.0"),
            max_positions=1,
            params={},
            status="stopped"  # Already stopped
        )
        test_db.add(stopped_strategy)
        test_db.commit()
        
        # Try to pause (should return empty list)
        paused_strategies = await strategy_runner.pause_all_strategies_for_account(
            account_id="account1",
            reason="Daily loss limit exceeded"
        )
        
        assert len(paused_strategies) == 0, "Should return empty list when no running strategies"
        
        # Verify stopped strategy remains stopped (not changed)
        stopped_strategy_after = test_db.query(Strategy).filter(
            Strategy.id == stopped_strategy.id
        ).first()
        assert stopped_strategy_after.status == "stopped", "Stopped strategy should remain stopped"
    
    @pytest.mark.asyncio
    async def test_pause_creates_enforcement_event(
        self,
        test_db,
        test_user,
        test_account_1,
        test_strategies_account_1,
        strategy_runner
    ):
        """Test that pausing creates proper enforcement event."""
        
        # Pause strategies
        paused_strategies = await strategy_runner.pause_all_strategies_for_account(
            account_id="account1",
            reason="Daily loss limit exceeded: -$150.00 >= -$100.00"
        )
        
        assert len(paused_strategies) > 0, "Should have paused strategies"
        
        # Verify enforcement event
        events = test_db.query(SystemEvent).filter(
            SystemEvent.event_type == "ACCOUNT_STRATEGIES_PAUSED",
            SystemEvent.account_id == test_account_1.id
        ).all()
        
        assert len(events) == 1, "Should have exactly one enforcement event"
        event = events[0]
        
        # Verify event properties
        assert event.event_type == "ACCOUNT_STRATEGIES_PAUSED"
        assert event.event_level == "WARNING"
        assert event.account_id == test_account_1.id
        assert event.strategy_id is None, "Account-level event should have NULL strategy_id"
        assert "account1" in event.message.lower()
        assert "daily loss limit" in event.message.lower()
        
        # Verify metadata
        metadata = event.event_metadata
        assert metadata is not None
        assert metadata.get("account_id") == "account1"
        assert metadata.get("reason") == "Daily loss limit exceeded: -$150.00 >= -$100.00"
        assert metadata.get("paused_count") == 3
        assert len(metadata.get("paused_strategies", [])) == 3
        assert all(sid in metadata["paused_strategies"] for sid in paused_strategies)
    
    @pytest.mark.asyncio
    async def test_pause_handles_invalid_account(
        self,
        test_db,
        test_user,
        strategy_runner
    ):
        """Test that pausing handles invalid account gracefully."""
        
        # Try to pause non-existent account
        paused_strategies = await strategy_runner.pause_all_strategies_for_account(
            account_id="nonexistent",
            reason="Daily loss limit exceeded"
        )
        
        assert len(paused_strategies) == 0, "Should return empty list for invalid account"
        
        # Verify no events were created
        events = test_db.query(SystemEvent).filter(
            SystemEvent.event_type == "ACCOUNT_STRATEGIES_PAUSED"
        ).all()
        assert len(events) == 0, "Should not create events for invalid account"
    
    @pytest.mark.asyncio
    async def test_pause_updates_status_correctly(
        self,
        test_db,
        test_user,
        test_account_1,
        test_strategies_account_1,
        strategy_runner
    ):
        """Test that pause correctly updates strategy status to stopped_by_risk."""
        
        # Get strategies before pause
        strategies_before = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_1.id
        ).all()
        
        # Verify all are running
        for strategy in strategies_before:
            assert strategy.status == "running", \
                f"Strategy {strategy.strategy_id} should be running before pause"
        
        # Pause strategies
        await strategy_runner.pause_all_strategies_for_account(
            account_id="account1",
            reason="Daily loss limit exceeded"
        )
        
        # Refresh from database
        test_db.expire_all()
        strategies_after = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_1.id
        ).all()
        
        # Verify all are stopped_by_risk
        for strategy in strategies_after:
            assert strategy.status == "stopped_by_risk", \
                f"Strategy {strategy.strategy_id} should be stopped_by_risk after pause, got {strategy.status}"
    
    @pytest.mark.asyncio
    async def test_pause_closes_positions_and_cancels_tp_sl(
        self,
        test_db,
        test_user,
        test_account_1,
        test_strategies_account_1,
        strategy_runner
    ):
        """Test that pausing strategies closes positions and cancels TP/SL orders."""
        
        # Mock BinanceClient and client manager
        mock_client = MagicMock()
        mock_client.get_open_position = MagicMock(return_value={
            "positionAmt": "0.001",
            "entryPrice": "40000.0",
            "unRealizedProfit": "-5.50",
            "markPrice": "40000.0"
        })
        mock_client.close_position = MagicMock(return_value=MagicMock(
            side="SELL",
            symbol="BTCUSDT",
            executed_qty=0.001,
            avg_price=40000.0,
            price=40000.0,
            order_id=12345,
            status="FILLED"
        ))
        
        # Mock client manager
        strategy_runner.client_manager = MagicMock()
        strategy_runner.client_manager.get_client = MagicMock(return_value=mock_client)
        strategy_runner._get_account_client = MagicMock(return_value=mock_client)
        
        # Mock order manager to track TP/SL cancellation
        mock_order_manager = MagicMock()
        mock_order_manager.cancel_tp_sl_orders = AsyncMock()
        strategy_runner.order_manager = mock_order_manager
        
        # Mock trade service
        mock_trade_service = MagicMock()
        mock_trade_service.save_trade = MagicMock()
        strategy_runner.trade_service = mock_trade_service
        
        # Add strategies to in-memory cache with positions
        from app.models.strategy import StrategySummary, StrategyState
        for i, db_strategy in enumerate(test_strategies_account_1):
            summary = StrategySummary(
                id=db_strategy.strategy_id,
                name=db_strategy.name,
                symbol=db_strategy.symbol,
                strategy_type=db_strategy.strategy_type,
                status=StrategyState.running,
                leverage=db_strategy.leverage,
                risk_per_trade=float(db_strategy.risk_per_trade),
                fixed_amount=float(db_strategy.fixed_amount) if db_strategy.fixed_amount else None,
                params=db_strategy.params or {},
                account_id="account1",
                created_at=datetime.now(timezone.utc),
                last_signal="HOLD",
                position_size=0.001,  # Has position
                position_side="LONG",
                entry_price=40000.0
            )
            strategy_runner._strategies[db_strategy.strategy_id] = summary
        
        # Pause strategies
        paused_strategies = await strategy_runner.pause_all_strategies_for_account(
            account_id="account1",
            reason="Daily loss limit exceeded"
        )
        
        # Verify strategies were paused
        assert len(paused_strategies) == 3, "Should pause 3 strategies"
        
        # Verify TP/SL orders were cancelled for each strategy
        assert mock_order_manager.cancel_tp_sl_orders.call_count == 3, \
            "Should cancel TP/SL orders for all 3 strategies"
        
        # Verify positions were closed for each strategy
        assert mock_client.get_open_position.call_count == 3, \
            "Should check position for all 3 strategies"
        assert mock_client.close_position.call_count == 3, \
            "Should close position for all 3 strategies"
        
        # Verify closing trades were saved
        assert mock_trade_service.save_trade.call_count == 3, \
            "Should save closing trade for all 3 strategies"
    
    @pytest.mark.asyncio
    async def test_pause_handles_strategies_without_positions(
        self,
        test_db,
        test_user,
        test_account_1,
        test_strategies_account_1,
        strategy_runner
    ):
        """Test that pausing works correctly when strategies have no open positions."""
        
        # Mock BinanceClient
        mock_client = MagicMock()
        mock_client.get_open_position = MagicMock(return_value=None)  # No position
        
        # Mock client manager
        strategy_runner.client_manager = MagicMock()
        strategy_runner.client_manager.get_client = MagicMock(return_value=mock_client)
        strategy_runner._get_account_client = MagicMock(return_value=mock_client)
        
        # Mock order manager
        mock_order_manager = MagicMock()
        mock_order_manager.cancel_tp_sl_orders = AsyncMock()
        strategy_runner.order_manager = mock_order_manager
        
        # Add strategies to in-memory cache without positions
        from app.models.strategy import StrategySummary, StrategyState
        for db_strategy in test_strategies_account_1:
            summary = StrategySummary(
                id=db_strategy.strategy_id,
                name=db_strategy.name,
                symbol=db_strategy.symbol,
                strategy_type=db_strategy.strategy_type,
                status=StrategyState.running,
                leverage=db_strategy.leverage,
                risk_per_trade=float(db_strategy.risk_per_trade),
                fixed_amount=float(db_strategy.fixed_amount) if db_strategy.fixed_amount else None,
                params=db_strategy.params or {},
                account_id="account1",
                created_at=datetime.now(timezone.utc),
                last_signal="HOLD",
                position_size=None,  # No position
                position_side=None,
                entry_price=None
            )
            strategy_runner._strategies[db_strategy.strategy_id] = summary
        
        # Pause strategies
        paused_strategies = await strategy_runner.pause_all_strategies_for_account(
            account_id="account1",
            reason="Daily loss limit exceeded"
        )
        
        # Verify strategies were paused
        assert len(paused_strategies) == 3, "Should pause 3 strategies"
        
        # Verify TP/SL orders were still cancelled (even without positions)
        assert mock_order_manager.cancel_tp_sl_orders.call_count == 3, \
            "Should cancel TP/SL orders even if no positions"
        
        # Verify position was checked but not closed (no position exists)
        assert mock_client.get_open_position.call_count == 3, \
            "Should check position for all strategies"
        assert mock_client.close_position.call_count == 0, \
            "Should not close position if none exists"
    
    @pytest.mark.asyncio
    async def test_pause_is_blocking_not_background_task(
        self,
        test_db,
        test_user,
        test_account_1,
        test_strategies_account_1,
        strategy_runner
    ):
        """Test that pause_all_strategies_for_account is blocking (awaited), not a background task."""
        
        import asyncio
        from unittest.mock import patch
        
        # Track when pause completes
        pause_completed = False
        
        async def track_pause():
            nonlocal pause_completed
            await strategy_runner.pause_all_strategies_for_account(
                account_id="account1",
                reason="Daily loss limit exceeded"
            )
            pause_completed = True
        
        # Run pause and verify it completes synchronously
        await track_pause()
        
        # Verify pause completed (not a background task)
        assert pause_completed, "Pause should complete synchronously (not background task)"
        
        # Verify strategies are paused in database
        paused_count = test_db.query(Strategy).filter(
            Strategy.account_id == test_account_1.id,
            Strategy.status == "stopped_by_risk"
        ).count()
        assert paused_count == 3, "All strategies should be paused synchronously"

