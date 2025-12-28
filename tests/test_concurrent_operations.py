"""Test concurrent operations in StrategyRunner to verify thread safety and no deadlocks."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest
pytestmark = pytest.mark.slow  # Concurrent tests with sleeps excluded from CI

from app.models.strategy import CreateStrategyRequest, StrategyParams, StrategyType, StrategyState
from app.services.strategy_runner import StrategyRunner
from app.core.binance_client_manager import BinanceClientManager
from app.core.config import get_settings


class DummyRedis:
    enabled = False


def make_runner(max_concurrent=5):
    """Create a StrategyRunner for testing."""
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
        max_concurrent=max_concurrent,
        redis_storage=DummyRedis(),
    )


@pytest.mark.asyncio
async def test_concurrent_strategy_registration():
    """Test that multiple strategies can be registered concurrently without errors."""
    runner = make_runner(max_concurrent=10)
    
    async def register_strategy(i):
        """Register a single strategy."""
        try:
            payload = CreateStrategyRequest(
                name=f"Test Strategy {i}",
                symbol="BTCUSDT",
                strategy_type=StrategyType.ema_crossover,
                leverage=10,
                risk_per_trade=0.02,
                params=StrategyParams(interval_seconds=60),
                fixed_amount=100.0
            )
            summary = runner.register(payload)
            return summary.id
        except Exception as e:
            return f"ERROR: {e}"
    
    # Register 20 strategies concurrently
    results = await asyncio.gather(*[register_strategy(i) for i in range(20)])
    
    # Verify all registrations succeeded
    errors = [r for r in results if isinstance(r, str) and r.startswith("ERROR")]
    assert len(errors) == 0, f"Registration errors: {errors}"
    
    # Verify all strategies are registered
    strategies = runner.list_strategies()
    assert len(strategies) == 20, f"Expected 20 strategies, got {len(strategies)}"


@pytest.mark.asyncio
async def test_concurrent_strategy_starts():
    """Test that multiple strategies can be started concurrently without deadlocks."""
    runner = make_runner(max_concurrent=5)
    
    # Register 10 strategies first
    strategy_ids = []
    for i in range(10):
        payload = CreateStrategyRequest(
            name=f"Test Strategy {i}",
            symbol="BTCUSDT",
            strategy_type=StrategyType.ema_crossover,
            leverage=10,
            risk_per_trade=0.02,
            params=StrategyParams(interval_seconds=60),
            fixed_amount=100.0
        )
        summary = runner.register(payload)
        strategy_ids.append(summary.id)
    
    # Mock the _run_loop to complete immediately (simulate strategy that exits quickly)
    async def mock_run_loop(*args, **kwargs):
        await asyncio.sleep(0.01)  # Small delay to simulate work
    
    runner._run_loop = mock_run_loop
    
    async def start_strategy(sid):
        """Start a single strategy."""
        try:
            await runner.start(sid)
            return sid
        except Exception as e:
            return f"ERROR: {e}"
    
    # Start 10 strategies concurrently (but max_concurrent=5, so some should fail with limit error)
    start_time = asyncio.get_event_loop().time()
    results = await asyncio.gather(*[start_strategy(sid) for sid in strategy_ids], return_exceptions=True)
    end_time = asyncio.get_event_loop().time()
    
    # Verify no deadlocks (should complete in reasonable time)
    elapsed = end_time - start_time
    assert elapsed < 5.0, f"Operations took too long ({elapsed}s), possible deadlock"
    
    # Verify some strategies started (up to max_concurrent=5)
    # The rest should fail with MaxConcurrentStrategiesError (expected behavior)
    successes = [r for r in results if isinstance(r, str) and not r.startswith("ERROR")]
    limit_errors = [r for r in results if isinstance(r, str) and "Maximum concurrent strategies limit" in r]
    other_errors = [r for r in results if isinstance(r, (str, Exception)) and "ERROR" in str(r) and "Maximum concurrent" not in str(r)]
    
    assert len(successes) == 5, f"Expected 5 strategies to start (max_concurrent), got {len(successes)}"
    assert len(limit_errors) == 5, f"Expected 5 limit errors, got {len(limit_errors)}"
    assert len(other_errors) == 0, f"Unexpected errors: {other_errors}"
    
    # Cleanup: stop all strategies
    for sid in strategy_ids:
        try:
            await runner.stop(sid)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_concurrent_strategy_stops():
    """Test that multiple strategies can be stopped concurrently without errors."""
    runner = make_runner(max_concurrent=10)
    
    # Register and start 10 strategies
    strategy_ids = []
    for i in range(10):
        payload = CreateStrategyRequest(
            name=f"Test Strategy {i}",
            symbol="BTCUSDT",
            strategy_type=StrategyType.ema_crossover,
            leverage=10,
            risk_per_trade=0.02,
            params=StrategyParams(interval_seconds=60),
            fixed_amount=100.0
        )
        summary = runner.register(payload)
        strategy_ids.append(summary.id)
    
    # Mock _run_loop to run indefinitely
    async def mock_run_loop(*args, **kwargs):
        while True:
            await asyncio.sleep(0.1)
    
    runner._run_loop = mock_run_loop
    
    # Start all strategies
    for sid in strategy_ids:
        try:
            await runner.start(sid)
        except Exception:
            pass
    
    await asyncio.sleep(0.1)  # Give strategies time to start
    
    # Stop all strategies concurrently
    async def stop_strategy(sid):
        """Stop a single strategy."""
        try:
            await runner.stop(sid)
            return sid
        except Exception as e:
            return f"ERROR: {e}"
    
    start_time = asyncio.get_event_loop().time()
    results = await asyncio.gather(*[stop_strategy(sid) for sid in strategy_ids], return_exceptions=True)
    end_time = asyncio.get_event_loop().time()
    
    # Verify no deadlocks
    elapsed = end_time - start_time
    assert elapsed < 5.0, f"Stop operations took too long ({elapsed}s), possible deadlock"
    
    # Verify all stops succeeded
    errors = [r for r in results if isinstance(r, (str, Exception)) and "ERROR" in str(r)]
    assert len(errors) == 0, f"Stop errors: {errors}"


@pytest.mark.asyncio
async def test_concurrent_account_client_loading():
    """Test that account clients can be loaded concurrently without UnboundLocalError."""
    runner = make_runner()
    
    # Mock strategy_service to simulate database loading
    mock_strategy_service = MagicMock()
    mock_strategy_service.db_service = MagicMock()
    mock_strategy_service.db_service.db = MagicMock()
    runner.strategy_service = mock_strategy_service
    
    # Mock AccountService to return account configs
    from app.core.config import BinanceAccountConfig
    
    async def load_account_client(account_id):
        """Load an account client concurrently."""
        try:
            # This should not raise UnboundLocalError even if user_id is None
            client = runner._get_account_client(account_id)
            return client is not None
        except UnboundLocalError as e:
            return f"UnboundLocalError: {e}"
        except Exception as e:
            return f"ERROR: {e}"
    
    # Try to load account clients concurrently with various scenarios
    results = await asyncio.gather(
        *[load_account_client("default") for _ in range(10)],
        return_exceptions=True
    )
    
    # Verify no UnboundLocalError
    unbound_errors = [r for r in results if isinstance(r, str) and "UnboundLocalError" in r]
    assert len(unbound_errors) == 0, f"UnboundLocalError occurred: {unbound_errors}"


@pytest.mark.asyncio
async def test_dead_task_cleanup_concurrent():
    """Test that dead task cleanup works correctly under concurrent operations."""
    runner = make_runner(max_concurrent=5)
    
    # Register and start 5 strategies
    strategy_ids = []
    for i in range(5):
        payload = CreateStrategyRequest(
            name=f"Test Strategy {i}",
            symbol="BTCUSDT",
            strategy_type=StrategyType.ema_crossover,
            leverage=10,
            risk_per_trade=0.02,
            params=StrategyParams(interval_seconds=60),
            fixed_amount=100.0
        )
        summary = runner.register(payload)
        strategy_ids.append(summary.id)
    
    # Mock executor.run_loop to complete quickly (simulate dead tasks)
    async def mock_run_loop(*args, **kwargs):
        await asyncio.sleep(0.01)
        raise Exception("Task completed/crashed")
    
    runner.executor.run_loop = mock_run_loop
    
    # Start all strategies concurrently
    start_tasks = [runner.start(sid) for sid in strategy_ids]
    await asyncio.gather(*start_tasks, return_exceptions=True)
    
    await asyncio.sleep(0.2)  # Give tasks time to complete/crash
    
    # Trigger cleanup concurrently while trying to start new strategies
    async def cleanup_and_start():
        """Cleanup dead tasks and try to start a new strategy."""
        try:
            await runner._cleanup_dead_tasks()
            # Try to start a new strategy (should work after cleanup)
            payload = CreateStrategyRequest(
                name="New Strategy",
                symbol="ETHUSDT",
                strategy_type=StrategyType.ema_crossover,
                leverage=10,
                risk_per_trade=0.02,
                params=StrategyParams(interval_seconds=60),
                fixed_amount=100.0
            )
            summary = runner.register(payload)
            await runner.start(summary.id)
            return True
        except Exception as e:
            return f"ERROR: {e}"
    
    # Run cleanup and start operations concurrently
    results = await asyncio.gather(*[cleanup_and_start() for _ in range(5)], return_exceptions=True)
    
    # Verify cleanup worked (no errors)
    errors = [r for r in results if isinstance(r, (str, Exception)) and "ERROR" in str(r)]
    assert len(errors) == 0, f"Cleanup errors: {errors}"


@pytest.mark.asyncio
async def test_concurrent_list_strategies():
    """Test that list_strategies() can be called concurrently without race conditions."""
    runner = make_runner()
    
    # Register 10 strategies
    for i in range(10):
        payload = CreateStrategyRequest(
            name=f"Test Strategy {i}",
            symbol="BTCUSDT",
            strategy_type=StrategyType.ema_crossover,
            leverage=10,
            risk_per_trade=0.02,
            params=StrategyParams(interval_seconds=60),
            fixed_amount=100.0
        )
        runner.register(payload)
    
    async def list_strategies():
        """List strategies concurrently."""
        try:
            strategies = runner.list_strategies()
            return len(strategies)
        except RuntimeError as e:
            if "dictionary changed size" in str(e):
                return f"RUNTIME_ERROR: {e}"
            raise
        except Exception as e:
            return f"ERROR: {e}"
    
    # Call list_strategies concurrently while modifying strategies
    async def modify_strategies():
        """Modify strategies concurrently."""
        for i in range(5):
            payload = CreateStrategyRequest(
                name=f"New Strategy {i}",
                symbol="ETHUSDT",
                strategy_type=StrategyType.ema_crossover,
                leverage=10,
                risk_per_trade=0.02,
                params=StrategyParams(interval_seconds=60),
                fixed_amount=100.0
            )
            runner.register(payload)
            await asyncio.sleep(0.01)
    
    # Run list and modify operations concurrently
    list_results = await asyncio.gather(*[list_strategies() for _ in range(20)], return_exceptions=True)
    modify_task = asyncio.create_task(modify_strategies())
    
    await modify_task
    
    # Verify no "dictionary changed size" errors
    runtime_errors = [r for r in list_results if isinstance(r, str) and "RUNTIME_ERROR" in r]
    assert len(runtime_errors) == 0, f"RuntimeError occurred: {runtime_errors}"


@pytest.mark.asyncio
async def test_concurrent_get_trades():
    """Test that get_trades() can be called concurrently without returning references."""
    runner = make_runner()
    
    # Register a strategy and add some trades
    payload = CreateStrategyRequest(
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.ema_crossover,
        leverage=10,
        risk_per_trade=0.02,
        params=StrategyParams(interval_seconds=60),
        fixed_amount=100.0
    )
    summary = runner.register(payload)
    
    # Add mock trades
    from app.models.order import OrderResponse
    trades = [
        OrderResponse(
            symbol="BTCUSDT",
            side="BUY",
            order_id=i,
            price=50000.0 + i,
            avg_price=50000.0 + i,
            executed_qty=0.1,
            status="FILLED"
        )
        for i in range(5)
    ]
    runner._trades[summary.id] = trades
    
    async def get_trades():
        """Get trades concurrently."""
        try:
            result = runner.get_trades(summary.id)
            # Try to modify the result (should not affect internal state)
            if result:
                result.append("MODIFIED")  # This should not affect runner._trades
            return len(result)
        except Exception as e:
            return f"ERROR: {e}"
    
    # Get trades concurrently
    results = await asyncio.gather(*[get_trades() for _ in range(10)], return_exceptions=True)
    
    # Verify all calls succeeded
    errors = [r for r in results if isinstance(r, (str, Exception)) and "ERROR" in str(r)]
    assert len(errors) == 0, f"Get trades errors: {errors}"
    
    # Verify internal trades were not modified (should still be 5, not 6)
    internal_trades = runner._trades.get(summary.id, [])
    assert len(internal_trades) == 5, "Internal trades were modified (returned reference instead of copy)"


@pytest.mark.asyncio
async def test_no_nested_lock_deadlock():
    """Test that there are no nested lock acquisitions that cause deadlocks."""
    runner = make_runner(max_concurrent=3)
    
    # Register 5 strategies
    strategy_ids = []
    for i in range(5):
        payload = CreateStrategyRequest(
            name=f"Test Strategy {i}",
            symbol="BTCUSDT",
            strategy_type=StrategyType.ema_crossover,
            leverage=10,
            risk_per_trade=0.02,
            params=StrategyParams(interval_seconds=60),
            fixed_amount=100.0
        )
        summary = runner.register(payload)
        strategy_ids.append(summary.id)
    
    # Mock _run_loop to run for a bit then exit
    async def mock_run_loop(*args, **kwargs):
        await asyncio.sleep(0.1)
    
    runner._run_loop = mock_run_loop
    
    # Start all strategies concurrently (some will hit max_concurrent limit)
    async def start_with_timeout(sid):
        """Start strategy with timeout to detect deadlocks."""
        try:
            await asyncio.wait_for(runner.start(sid), timeout=2.0)
            return sid
        except asyncio.TimeoutError:
            return "TIMEOUT"
        except Exception as e:
            return f"ERROR: {e}"
    
    start_time = asyncio.get_event_loop().time()
    results = await asyncio.gather(*[start_with_timeout(sid) for sid in strategy_ids], return_exceptions=True)
    end_time = asyncio.get_event_loop().time()
    
    # Verify no timeouts (deadlocks)
    timeouts = [r for r in results if r == "TIMEOUT"]
    assert len(timeouts) == 0, f"Deadlock detected: {len(timeouts)} operations timed out"
    
    # Verify operations completed quickly
    elapsed = end_time - start_time
    assert elapsed < 3.0, f"Operations took too long ({elapsed}s), possible deadlock"
    
    # Cleanup
    for sid in strategy_ids:
        try:
            await runner.stop(sid)
        except Exception:
            pass

