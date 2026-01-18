"""Test case to verify that when daily limit is exceeded, strategies are stopped using stop() function.

Tests verify that:
1. When daily limit exceeded, stop() is called for each strategy
2. All strategies for the account are stopped (not just paused)
3. Status is correctly set to "stopped_by_risk" after stopping
4. Tasks are cancelled and removed from _tasks dict
5. Positions are closed and TP/SL orders are cancelled
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch, call
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CheckConstraint

from app.models.db_models import Strategy, User, Account, SystemEvent, Base
from app.models.strategy import StrategyState, StrategySummary
from app.services.strategy_runner import StrategyRunner
from app.services.strategy_order_manager import StrategyOrderManager
from app.services.strategy_service import StrategyService
from app.services.database_service import DatabaseService
from app.core.redis_storage import RedisStorage
from app.core.binance_client_manager import BinanceClientManager

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
def test_account(test_db, test_user):
    """Create test account."""
    account = Account(
        id=uuid4(),
        user_id=test_user.id,
        account_id="default",
        name="Test Account",
        api_key_encrypted="test_api_key",
        api_secret_encrypted="test_api_secret",
        testnet=True,
        is_active=True,
        is_default=True
    )
    test_db.add(account)
    test_db.commit()
    return account


@pytest.fixture
def test_strategies(test_db, test_user, test_account):
    """Create multiple running strategies for testing."""
    strategies = []
    for i in range(3):
        strategy = Strategy(
            id=uuid4(),
            user_id=test_user.id,
            account_id=test_account.id,
            strategy_id=f"strategy-{i+1}",
            name=f"Strategy {i+1}",
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
def strategy_runner(test_db, test_user):
    """Create StrategyRunner instance for testing."""
    db_service = DatabaseService(test_db)
    strategy_service = StrategyService(test_db)
    
    # Mock Redis storage
    redis_storage = MagicMock(spec=RedisStorage)
    redis_storage.enabled = False
    
    # Mock BinanceClientManager
    client_manager = MagicMock(spec=BinanceClientManager)
    
    # Mock client with position
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
    client_manager.get_client = MagicMock(return_value=mock_client)
    
    runner = StrategyRunner(
        client_manager=client_manager,
        strategy_service=strategy_service,
        user_id=test_user.id,
        redis_storage=redis_storage,
    )
    
    # Mock _get_account_client to return mock client
    runner._get_account_client = MagicMock(return_value=mock_client)
    
    # Mock order manager
    mock_order_manager = MagicMock(spec=StrategyOrderManager)
    mock_order_manager.cancel_tp_sl_orders = AsyncMock()
    mock_order_manager.strategy_service = strategy_service
    mock_order_manager.user_id = test_user.id
    runner.order_manager = mock_order_manager
    
    # Mock trade service
    mock_trade_service = MagicMock()
    mock_trade_service.save_trade = MagicMock()
    runner.trade_service = mock_trade_service
    
    # Mock state manager  
    runner.state_manager = MagicMock()
    runner.state_manager.update_strategy_in_db = MagicMock(return_value=True)
    
    return runner


class TestDailyLimitStopsStrategies:
    """Test that daily limit exceeded stops strategies using stop() function."""
    
    @pytest.mark.asyncio
    async def test_daily_limit_exceeded_calls_stop_for_each_strategy(
        self,
        test_db,
        test_user,
        test_account,
        test_strategies,
        strategy_runner
    ):
        """Test that when daily limit is exceeded, stop() is called for each strategy."""
        
        # Add strategies to in-memory cache with running status
        for db_strategy in test_strategies:
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
                account_id="default",
                position_size=0.001,
                position_side="LONG",
                entry_price=40000.0,
                created_at=datetime.now(timezone.utc),
                last_signal="HOLD"
            )
            strategy_runner._strategies[db_strategy.strategy_id] = summary
            
            # Create mock tasks for running strategies
            mock_task = AsyncMock()
            mock_task.done = MagicMock(return_value=False)
            mock_task.cancel = MagicMock()
            strategy_runner._tasks[db_strategy.strategy_id] = mock_task
        
        # Verify initial state: all strategies are running
        assert len(strategy_runner._strategies) == 3, "Should have 3 strategies in memory"
        assert len(strategy_runner._tasks) == 3, "Should have 3 running tasks"
        
        # Verify database status is "running"
        db_strategies = test_db.query(Strategy).filter(
            Strategy.account_id == test_account.id
        ).all()
        assert all(s.status == "running" for s in db_strategies), "All strategies should be running"
        
        # Mock stop() to track calls
        original_stop = strategy_runner.stop
        stop_calls = []
        
        async def tracked_stop(strategy_id):
            """Track stop() calls."""
            stop_calls.append(strategy_id)
            # Call original stop but skip database update (we'll verify separately)
            return await original_stop(strategy_id)
        
        strategy_runner.stop = tracked_stop
        
        # Simulate daily limit exceeded - call pause_all_strategies_for_account
        paused_strategies = await strategy_runner.pause_all_strategies_for_account(
            account_id="default",
            reason="Daily loss limit exceeded: -$150.00 >= -$100.00"
        )
        
        # Verify stop() was called for each strategy
        assert len(stop_calls) == 3, f"stop() should be called 3 times, got {len(stop_calls)}"
        assert "strategy-1" in stop_calls
        assert "strategy-2" in stop_calls
        assert "strategy-3" in stop_calls
        
        # Verify strategies were returned as paused
        assert len(paused_strategies) == 3, "Should return 3 paused strategies"
        assert all(sid in paused_strategies for sid in ["strategy-1", "strategy-2", "strategy-3"])
        
        # Verify database status is "stopped_by_risk"
        test_db.expire_all()  # Refresh from database
        db_strategies_after = test_db.query(Strategy).filter(
            Strategy.account_id == test_account.id
        ).all()
        for strategy in db_strategies_after:
            assert strategy.status == "stopped_by_risk", \
                f"Strategy {strategy.strategy_id} should be stopped_by_risk, got {strategy.status}"
        
        # Verify in-memory summaries are updated
        for strategy_id in ["strategy-1", "strategy-2", "strategy-3"]:
            summary = strategy_runner._strategies.get(strategy_id)
            assert summary is not None, f"Strategy {strategy_id} should exist in memory"
            assert summary.status == StrategyState.stopped_by_risk, \
                f"Strategy {strategy_id} should be stopped_by_risk in memory, got {summary.status}"
        
        # Verify tasks were cancelled and removed
        assert len(strategy_runner._tasks) == 0, \
            "All tasks should be removed from _tasks dict"
        
        # Verify TP/SL orders were cancelled (stop() calls cancel_tp_sl_orders)
        assert strategy_runner.order_manager.cancel_tp_sl_orders.call_count >= 3, \
            "Should cancel TP/SL orders for all strategies (called by stop())"
        
        # Verify positions were closed (stop() calls close_position)
        assert strategy_runner._get_account_client().close_position.call_count >= 3, \
            "Should close positions for all strategies (called by stop())"
    
    @pytest.mark.asyncio
    async def test_daily_limit_stops_only_account_strategies(
        self,
        test_db,
        test_user,
        test_account,
        test_strategies,
        strategy_runner
    ):
        """Test that daily limit exceeded only stops strategies for that account."""
        
        # Create a second account with its own strategies
        account2 = Account(
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
        test_db.add(account2)
        
        strategy_account2 = Strategy(
            id=uuid4(),
            user_id=test_user.id,
            account_id=account2.id,
            strategy_id="strategy-account2-1",
            name="Strategy Account2 1",
            symbol="ETHUSDT",
            strategy_type="scalping",
            leverage=5,
            risk_per_trade=Decimal("0.01"),
            fixed_amount=Decimal("1000.0"),
            max_positions=1,
            params={},
            status="running"
        )
        test_db.add(strategy_account2)
        test_db.commit()
        
        # Add strategies to in-memory cache
        for db_strategy in test_strategies:
            summary = StrategySummary(
                id=db_strategy.strategy_id,
                name=db_strategy.name,
                symbol=db_strategy.symbol,
                strategy_type=db_strategy.strategy_type,
                status=StrategyState.running,
                leverage=db_strategy.leverage,
                risk_per_trade=float(db_strategy.risk_per_trade),
                fixed_amount=float(db_strategy.fixed_amount),
                params=db_strategy.params or {},
                account_id="default",
                created_at=datetime.now(timezone.utc),
                last_signal="HOLD"
            )
            strategy_runner._strategies[db_strategy.strategy_id] = summary
            # Create mock tasks
            mock_task = AsyncMock()
            mock_task.done = MagicMock(return_value=False)
            strategy_runner._tasks[db_strategy.strategy_id] = mock_task
        
        # Add account2 strategy
        summary_account2 = StrategySummary(
            id=strategy_account2.strategy_id,
            name=strategy_account2.name,
            symbol=strategy_account2.symbol,
            strategy_type=strategy_account2.strategy_type,
            status=StrategyState.running,
            leverage=strategy_account2.leverage,
            risk_per_trade=float(strategy_account2.risk_per_trade),
            fixed_amount=float(strategy_account2.fixed_amount),
            params=strategy_account2.params or {},
            account_id="account2",
            created_at=datetime.now(timezone.utc),
            last_signal="HOLD"
        )
        strategy_runner._strategies[strategy_account2.strategy_id] = summary_account2
        mock_task_account2 = AsyncMock()
        mock_task_account2.done = MagicMock(return_value=False)
        strategy_runner._tasks[strategy_account2.strategy_id] = mock_task_account2
        
        # Track stop() calls
        original_stop = strategy_runner.stop
        stop_calls = []
        
        async def tracked_stop(strategy_id):
            stop_calls.append(strategy_id)
            return await original_stop(strategy_id)
        
        strategy_runner.stop = tracked_stop
        
        # Pause only "default" account strategies
        paused_strategies = await strategy_runner.pause_all_strategies_for_account(
            account_id="default",
            reason="Daily loss limit exceeded: -$150.00 >= -$100.00"
        )
        
        # Verify stop() was called only for "default" account strategies
        assert len(stop_calls) == 3, "Should stop 3 strategies for default account"
        assert all(sid in stop_calls for sid in ["strategy-1", "strategy-2", "strategy-3"])
        assert "strategy-account2-1" not in stop_calls, "Should not stop account2 strategy"
        
        # Verify "default" account strategies are stopped_by_risk
        default_strategies = test_db.query(Strategy).filter(
            Strategy.account_id == test_account.id
        ).all()
        for strategy in default_strategies:
            assert strategy.status == "stopped_by_risk", \
                f"Strategy {strategy.strategy_id} should be stopped_by_risk"
        
        # Verify account2 strategy is still running
        account2_strategy_after = test_db.query(Strategy).filter(
            Strategy.id == strategy_account2.id
        ).first()
        assert account2_strategy_after.status == "running", \
            "Account2 strategy should still be running"
        
        # Verify account2 strategy is still in memory and running
        assert strategy_runner._strategies["strategy-account2-1"].status == StrategyState.running
        assert "strategy-account2-1" in strategy_runner._tasks, \
            "Account2 strategy task should still exist"
    
    @pytest.mark.asyncio
    async def test_daily_limit_status_is_stopped_by_risk_not_stopped(
        self,
        test_db,
        test_user,
        test_account,
        test_strategies,
        strategy_runner
    ):
        """Test that status is set to stopped_by_risk, not stopped, after daily limit exceeded."""
        
        # Add strategies to in-memory cache
        for db_strategy in test_strategies:
            summary = StrategySummary(
                id=db_strategy.strategy_id,
                name=db_strategy.name,
                symbol=db_strategy.symbol,
                strategy_type=db_strategy.strategy_type,
                status=StrategyState.running,
                leverage=db_strategy.leverage,
                risk_per_trade=float(db_strategy.risk_per_trade),
                fixed_amount=float(db_strategy.fixed_amount),
                params=db_strategy.params or {},
                account_id="default",
                created_at=datetime.now(timezone.utc),
                last_signal="HOLD"
            )
            strategy_runner._strategies[db_strategy.strategy_id] = summary
            mock_task = AsyncMock()
            mock_task.done = MagicMock(return_value=False)
            strategy_runner._tasks[db_strategy.strategy_id] = mock_task
        
        # Pause strategies
        paused_strategies = await strategy_runner.pause_all_strategies_for_account(
            account_id="default",
            reason="Daily loss limit exceeded: -$150.00 >= -$100.00"
        )
        
        assert len(paused_strategies) == 3, "Should pause 3 strategies"
        
        # Verify status is "stopped_by_risk", NOT "stopped"
        test_db.expire_all()
        db_strategies_after = test_db.query(Strategy).filter(
            Strategy.account_id == test_account.id
        ).all()
        
        for strategy in db_strategies_after:
            assert strategy.status == "stopped_by_risk", \
                f"Strategy {strategy.strategy_id} should be stopped_by_risk, got {strategy.status}"
            assert strategy.status != "stopped", \
                f"Strategy {strategy.strategy_id} should NOT be stopped, should be stopped_by_risk"
        
        # Verify in-memory status
        for strategy_id in paused_strategies:
            summary = strategy_runner._strategies.get(strategy_id)
            assert summary.status == StrategyState.stopped_by_risk, \
                f"In-memory status should be stopped_by_risk, got {summary.status}"
            assert summary.status != StrategyState.stopped, \
                f"In-memory status should NOT be stopped"
    
    @pytest.mark.asyncio
    async def test_daily_limit_stops_strategies_with_positions(
        self,
        test_db,
        test_user,
        test_account,
        test_strategies,
        strategy_runner
    ):
        """Test that strategies with open positions are properly stopped and positions closed."""
        
        mock_client = strategy_runner._get_account_client()
        
        # Add strategies with positions
        for db_strategy in test_strategies:
            summary = StrategySummary(
                id=db_strategy.strategy_id,
                name=db_strategy.name,
                symbol=db_strategy.symbol,
                strategy_type=db_strategy.strategy_type,
                status=StrategyState.running,
                leverage=db_strategy.leverage,
                risk_per_trade=float(db_strategy.risk_per_trade),
                fixed_amount=float(db_strategy.fixed_amount),
                params=db_strategy.params or {},
                account_id="default",
                position_size=0.001,
                position_side="LONG",
                entry_price=40000.0,
                created_at=datetime.now(timezone.utc),
                last_signal="HOLD"
            )
            strategy_runner._strategies[db_strategy.strategy_id] = summary
            mock_task = AsyncMock()
            mock_task.done = MagicMock(return_value=False)
            strategy_runner._tasks[db_strategy.strategy_id] = mock_task
        
        # Pause strategies
        paused_strategies = await strategy_runner.pause_all_strategies_for_account(
            account_id="default",
            reason="Daily loss limit exceeded"
        )
        
        assert len(paused_strategies) == 3
        
        # Verify positions were checked
        assert mock_client.get_open_position.call_count >= 3, \
            "Should check position for all 3 strategies"
        
        # Verify positions were closed (stop() calls close_position)
        assert mock_client.close_position.call_count >= 3, \
            "Should close positions for all 3 strategies via stop()"
        
        # Verify TP/SL orders were cancelled
        assert strategy_runner.order_manager.cancel_tp_sl_orders.call_count >= 3, \
            "Should cancel TP/SL orders for all 3 strategies via stop()"
        
        # Verify tasks were cancelled and removed
        assert len(strategy_runner._tasks) == 0, \
            "All tasks should be removed after stopping"
        
        # Verify status is stopped_by_risk
        test_db.expire_all()
        db_strategies = test_db.query(Strategy).filter(
            Strategy.account_id == test_account.id
        ).all()
        assert all(s.status == "stopped_by_risk" for s in db_strategies), \
            "All strategies should be stopped_by_risk"

