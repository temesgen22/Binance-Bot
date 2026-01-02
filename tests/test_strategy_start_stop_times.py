"""Tests for strategy start/stop timestamp functionality."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.strategy import CreateStrategyRequest, StrategyParams, StrategyType, StrategyState
from app.services.strategy_runner import StrategyRunner
from app.services.strategy_executor import StrategyExecutor
from app.core.binance_client_manager import BinanceClientManager
from app.core.config import get_settings


class DummyRedis:
    enabled = False


def make_runner_with_service():
    """Create a StrategyRunner with StrategyService for testing timestamps."""
    from app.services.strategy_service import StrategyService
    from app.services.database_service import DatabaseService
    from sqlalchemy.orm import Session
    
    # Create mock database session
    mock_db = MagicMock(spec=Session)
    mock_db_service = MagicMock(spec=DatabaseService)
    
    # Create StrategyService with mocked database
    strategy_service = StrategyService(db=mock_db, redis_storage=DummyRedis())
    strategy_service.db_service = mock_db_service
    
    # Create mock client
    client = MagicMock()
    risk = MagicMock()
    executor = MagicMock()
    
    # Create client manager
    settings = get_settings()
    manager = BinanceClientManager(settings)
    
    from app.core.config import BinanceAccountConfig
    default_account = BinanceAccountConfig(
        account_id="default",
        api_key="test_key",
        api_secret="test_secret",
        testnet=True
    )
    manager._clients = {'default': client}
    manager._accounts = {'default': default_account}
    
    # Create mock user_id
    user_id = uuid4()
    
    return StrategyRunner(
        client=client,
        client_manager=manager,
        risk=risk,
        executor=executor,
        max_concurrent=2,
        redis_storage=DummyRedis(),
        strategy_service=strategy_service,
        user_id=user_id,
    ), strategy_service, mock_db_service, user_id


def make_runner():
    """Create a StrategyRunner for testing (backward compatible, no database)."""
    client = MagicMock()
    risk = MagicMock()
    executor = MagicMock()
    
    settings = get_settings()
    manager = BinanceClientManager(settings)
    
    from app.core.config import BinanceAccountConfig
    default_account = BinanceAccountConfig(
        account_id="default",
        api_key="test_key",
        api_secret="test_secret",
        testnet=True
    )
    manager._clients = {'default': client}
    manager._accounts = {'default': default_account}
    
    return StrategyRunner(
        client=client,
        client_manager=manager,
        risk=risk,
        executor=executor,
        max_concurrent=2,
        redis_storage=DummyRedis(),
    )


@pytest.mark.asyncio
async def test_start_sets_started_at_timestamp():
    """Test that starting a strategy sets started_at timestamp."""
    runner, strategy_service, db_service, user_id = make_runner_with_service()
    
    # Create a strategy
    params = StrategyParams(ema_fast=3, ema_slow=5)
    payload = CreateStrategyRequest(
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        leverage=5,
        risk_per_trade=0.01,
        params=params,
    )
    
    summary = runner.register(payload)
    strategy_id = summary.id
    
    # Mock database update
    mock_db_strategy = MagicMock()
    mock_db_strategy.started_at = None
    mock_db_strategy.stopped_at = None
    db_service.update_strategy.return_value = mock_db_strategy
    strategy_service._db_strategy_to_summary = lambda x: summary
    
    # Mock the run loop to avoid actual execution
    async def short_run_loop(strategy, summary_obj, risk=None, executor=None):
        summary_obj.status = StrategyState.running
    
    with patch.object(StrategyExecutor, "run_loop", side_effect=short_run_loop):
        # Capture the timestamp before starting
        before_start = datetime.now(timezone.utc)
        
        started = await runner.start(strategy_id)
        
        # Capture the timestamp after starting
        after_start = datetime.now(timezone.utc)
        
        # Verify started_at is set
        assert started.started_at is not None
        assert before_start <= started.started_at <= after_start
        
        # Verify update_strategy was called with started_at
        db_service.update_strategy.assert_called()
        call_kwargs = db_service.update_strategy.call_args[1]
        assert "started_at" in call_kwargs
        assert call_kwargs["status"] == StrategyState.running.value
        
        # Clean up
        task = runner._tasks.pop(strategy_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


@pytest.mark.asyncio
async def test_stop_sets_stopped_at_timestamp():
    """Test that stopping a strategy sets stopped_at timestamp."""
    runner, strategy_service, db_service, user_id = make_runner_with_service()
    
    # Create and start a strategy
    params = StrategyParams(ema_fast=3, ema_slow=5)
    payload = CreateStrategyRequest(
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        leverage=5,
        risk_per_trade=0.01,
        params=params,
    )
    
    summary = runner.register(payload)
    strategy_id = summary.id
    
    # Mock database update
    mock_db_strategy = MagicMock()
    mock_db_strategy.started_at = datetime.now(timezone.utc)
    mock_db_strategy.stopped_at = None
    db_service.update_strategy.return_value = mock_db_strategy
    strategy_service._db_strategy_to_summary = lambda x: summary
    
    # Mock the run loop
    async def short_run_loop(strategy, summary_obj, risk, executor):
        summary_obj.status = StrategyState.running
    
    with patch.object(StrategyExecutor, "run_loop", side_effect=short_run_loop):
        # Start the strategy
        started = await runner.start(strategy_id)
        started.started_at = datetime.now(timezone.utc)
        
        # Capture the timestamp before stopping
        before_stop = datetime.now(timezone.utc)
        
        # Stop the strategy
        stopped = await runner.stop(strategy_id)
        
        # Capture the timestamp after stopping
        after_stop = datetime.now(timezone.utc)
        
        # Verify stopped_at is set
        assert stopped.stopped_at is not None
        assert before_stop <= stopped.stopped_at <= after_stop
        
        # Verify update_strategy was called with stopped_at
        # Check the last call (should be the stop call)
        all_calls = db_service.update_strategy.call_args_list
        stop_call = all_calls[-1]  # Last call should be the stop
        call_kwargs = stop_call[1] if len(stop_call) > 1 else {}
        assert "stopped_at" in call_kwargs
        assert call_kwargs["status"] == StrategyState.stopped.value


@pytest.mark.asyncio
async def test_multiple_start_stop_cycles_update_timestamps():
    """Test that multiple start/stop cycles update timestamps correctly."""
    runner, strategy_service, db_service, user_id = make_runner_with_service()
    
    # Create a strategy
    params = StrategyParams(ema_fast=3, ema_slow=5)
    payload = CreateStrategyRequest(
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        leverage=5,
        risk_per_trade=0.01,
        params=params,
    )
    
    summary = runner.register(payload)
    strategy_id = summary.id
    
    # Mock database update
    mock_db_strategy = MagicMock()
    db_service.update_strategy.return_value = mock_db_strategy
    strategy_service._db_strategy_to_summary = lambda x: summary
    
    # Mock the run loop
    async def short_run_loop(strategy, summary_obj, risk, executor):
        summary_obj.status = StrategyState.running
    
    with patch.object(StrategyExecutor, "run_loop", side_effect=short_run_loop):
        # First start
        started1 = await runner.start(strategy_id)
        first_started_at = started1.started_at
        assert first_started_at is not None
        
        # Wait a bit to ensure different timestamps
        await asyncio.sleep(0.01)
        
        # Stop
        stopped1 = await runner.stop(strategy_id)
        first_stopped_at = stopped1.stopped_at
        assert first_stopped_at is not None
        assert first_stopped_at > first_started_at
        
        # Wait a bit to ensure different timestamps
        await asyncio.sleep(0.1)
        
        # Second start (should update started_at)
        started2 = await runner.start(strategy_id)
        second_started_at = started2.started_at
        assert second_started_at is not None
        assert second_started_at > first_stopped_at
        
        # Second stop (should update stopped_at)
        stopped2 = await runner.stop(strategy_id)
        second_stopped_at = stopped2.stopped_at
        assert second_stopped_at is not None
        assert second_stopped_at > second_started_at


@pytest.mark.asyncio
async def test_started_at_persists_in_database():
    """Test that started_at timestamp is saved to database."""
    runner, strategy_service, db_service, user_id = make_runner_with_service()
    
    params = StrategyParams(ema_fast=3, ema_slow=5)
    payload = CreateStrategyRequest(
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        leverage=5,
        risk_per_trade=0.01,
        params=params,
    )
    
    summary = runner.register(payload)
    strategy_id = summary.id
    
    # Mock database update
    mock_db_strategy = MagicMock()
    db_service.update_strategy.return_value = mock_db_strategy
    strategy_service._db_strategy_to_summary = lambda x: summary
    
    async def short_run_loop(strategy, summary_obj, risk, executor):
        summary_obj.status = StrategyState.running
    
    with patch.object(StrategyExecutor, "run_loop", side_effect=short_run_loop):
        started = await runner.start(strategy_id)
        
        # Verify database update was called
        db_service.update_strategy.assert_called()
        call_args = db_service.update_strategy.call_args
        
        # Verify user_id and strategy_id are passed
        assert call_args[0][0] == user_id  # user_id
        assert call_args[0][1] == strategy_id  # strategy_id
        
        # Verify started_at is in the updates
        call_kwargs = call_args[1] if len(call_args) > 1 else {}
        assert "started_at" in call_kwargs
        assert isinstance(call_kwargs["started_at"], datetime)
        
        # Clean up
        task = runner._tasks.pop(strategy_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


@pytest.mark.asyncio
async def test_stopped_at_persists_in_database():
    """Test that stopped_at timestamp is saved to database."""
    runner, strategy_service, db_service, user_id = make_runner_with_service()
    
    params = StrategyParams(ema_fast=3, ema_slow=5)
    payload = CreateStrategyRequest(
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        leverage=5,
        risk_per_trade=0.01,
        params=params,
    )
    
    summary = runner.register(payload)
    strategy_id = summary.id
    
    # Mock database update
    mock_db_strategy = MagicMock()
    db_service.update_strategy.return_value = mock_db_strategy
    strategy_service._db_strategy_to_summary = lambda x: summary
    
    async def short_run_loop(strategy, summary_obj, risk, executor):
        summary_obj.status = StrategyState.running
    
    with patch.object(StrategyExecutor, "run_loop", side_effect=short_run_loop):
        # Start first
        await runner.start(strategy_id)
        
        # Stop
        stopped = await runner.stop(strategy_id)
        
        # Verify database update was called
        all_calls = db_service.update_strategy.call_args_list
        stop_call = all_calls[-1]  # Last call should be the stop
        
        # Verify stopped_at is in the updates
        call_kwargs = stop_call[1] if len(stop_call) > 1 else {}
        assert "stopped_at" in call_kwargs
        assert isinstance(call_kwargs["stopped_at"], datetime)


@pytest.mark.asyncio
async def test_strategy_summary_includes_timestamps():
    """Test that StrategySummary includes started_at and stopped_at fields."""
    from app.models.strategy import StrategySummary
    
    # Create a summary with timestamps
    started_at = datetime.now(timezone.utc)
    stopped_at = datetime.now(timezone.utc)
    
    summary = StrategySummary(
        id="test-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.stopped,
        leverage=5,
        risk_per_trade=0.01,
        params=StrategyParams(ema_fast=8, ema_slow=21),
        created_at=datetime.now(timezone.utc),
        last_signal=None,
        started_at=started_at,
        stopped_at=stopped_at,
    )
    
    # Verify fields exist
    assert summary.started_at == started_at
    assert summary.stopped_at == stopped_at
    
    # Verify they can be None
    summary_no_timestamps = StrategySummary(
        id="test-456",
        name="Test Strategy 2",
        symbol="ETHUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.stopped,
        leverage=5,
        risk_per_trade=0.01,
        params=StrategyParams(ema_fast=8, ema_slow=21),
        created_at=datetime.now(timezone.utc),
        last_signal=None,
        started_at=None,
        stopped_at=None,
    )
    
    assert summary_no_timestamps.started_at is None
    assert summary_no_timestamps.stopped_at is None


@pytest.mark.asyncio
async def test_strategy_performance_includes_timestamps():
    """Test that StrategyPerformance includes started_at and stopped_at fields."""
    from app.models.strategy_performance import StrategyPerformance
    
    started_at = datetime.now(timezone.utc)
    stopped_at = datetime.now(timezone.utc)
    
    performance = StrategyPerformance(
        strategy_id="test-123",
        strategy_name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.stopped,
        leverage=5,
        risk_per_trade=0.01,
        params={},
        created_at=datetime.now(timezone.utc),
        started_at=started_at,
        stopped_at=stopped_at,
    )
    
    # Verify fields exist
    assert performance.started_at == started_at
    assert performance.stopped_at == stopped_at


@pytest.mark.asyncio
async def test_backward_compatibility_no_database():
    """Test that strategies work without database (backward compatibility)."""
    runner = make_runner()
    
    params = StrategyParams(ema_fast=3, ema_slow=5)
    payload = CreateStrategyRequest(
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        leverage=5,
        risk_per_trade=0.01,
        params=params,
    )
    
    summary = runner.register(payload)
    strategy_id = summary.id
    
    # Should not have started_at initially
    assert summary.started_at is None
    assert summary.stopped_at is None
    
    # Mock the run loop
    async def short_run_loop(strategy, summary_obj, risk, executor):
        summary_obj.status = StrategyState.running
    
    with patch.object(StrategyExecutor, "run_loop", side_effect=short_run_loop):
        # Start should work even without database
        started = await runner.start(strategy_id)
        # Without database, started_at might not be set, but should not crash
        # (It will be set in memory but not persisted)
        
        # Clean up
        task = runner._tasks.pop(strategy_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

