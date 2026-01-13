"""Tests for periodic dead task cleanup functionality."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone

from app.services.strategy_runner import StrategyRunner
from app.models.strategy import CreateStrategyRequest, StrategyType, StrategyParams, StrategyState
from app.core.binance_client_manager import BinanceClientManager
from app.core.config import get_settings, BinanceAccountConfig


class DummyRedis:
    enabled = False


def make_runner():
    """Create a StrategyRunner for testing."""
    client = MagicMock()
    risk = MagicMock()
    executor = MagicMock()
    
    # Create a minimal client manager
    settings = get_settings()
    manager = BinanceClientManager(settings)
    
    # Manually add default account
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
        max_concurrent=5,
        redis_storage=DummyRedis(),
    )


class TestPeriodicCleanup:
    """Tests for periodic dead task cleanup."""
    
    @pytest.mark.asyncio
    async def test_periodic_cleanup_starts(self):
        """Test that periodic cleanup starts correctly."""
        runner = make_runner()
        
        # Start periodic cleanup with short interval for testing
        runner.start_periodic_cleanup(interval_seconds=0.1)
        
        # Verify cleanup task is created and running
        assert runner._cleanup_task is not None
        assert not runner._cleanup_task.done()
        assert runner._cleanup_running is True
        
        # Stop cleanup
        await runner.stop_periodic_cleanup()
        assert runner._cleanup_running is False
    
    @pytest.mark.asyncio
    async def test_periodic_cleanup_cleans_dead_tasks(self):
        """Test that periodic cleanup actually cleans up dead tasks."""
        runner = make_runner()
        
        # Create a dead task manually
        dead_task = asyncio.create_task(asyncio.sleep(0.01))
        await dead_task  # Wait for it to complete
        
        # Register a strategy and add the dead task
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
        strategy_id = summary.id
        
        # Manually add dead task to _tasks (simulating a crashed task)
        async with runner._lock:
            runner._tasks[strategy_id] = dead_task
            # Set status to running (simulating zombie state)
            summary.status = StrategyState.running
            runner._strategies[strategy_id] = summary
        
        # Verify task is marked as done
        assert dead_task.done()
        assert strategy_id in runner._tasks
        
        # Start periodic cleanup with very short interval
        runner.start_periodic_cleanup(interval_seconds=0.1)
        
        # Wait for cleanup to run (should happen within 0.2 seconds)
        await asyncio.sleep(0.25)
        
        # Verify dead task was cleaned up
        assert strategy_id not in runner._tasks
        
        # Verify status was updated to error
        assert runner._strategies[strategy_id].status == StrategyState.error
        
        # Stop cleanup
        await runner.stop_periodic_cleanup()
    
    @pytest.mark.asyncio
    async def test_periodic_cleanup_doesnt_affect_running_tasks(self):
        """Test that periodic cleanup doesn't interfere with running strategies."""
        runner = make_runner()
        
        # Create a running task (not done)
        running_task = asyncio.create_task(asyncio.sleep(10))  # Long sleep
        
        # Register a strategy
        payload = CreateStrategyRequest(
            name="Running Strategy",
            symbol="ETHUSDT",
            strategy_type=StrategyType.ema_crossover,
            leverage=10,
            risk_per_trade=0.02,
            params=StrategyParams(interval_seconds=60),
            fixed_amount=100.0
        )
        summary = runner.register(payload)
        strategy_id = summary.id
        
        # Add running task
        async with runner._lock:
            runner._tasks[strategy_id] = running_task
            summary.status = StrategyState.running
            runner._strategies[strategy_id] = summary
        
        # Verify task is not done
        assert not running_task.done()
        
        # Start periodic cleanup
        runner.start_periodic_cleanup(interval_seconds=0.1)
        
        # Wait for cleanup to run multiple times
        await asyncio.sleep(0.35)
        
        # Verify running task is still there
        assert strategy_id in runner._tasks
        assert not running_task.done()
        assert runner._strategies[strategy_id].status == StrategyState.running
        
        # Cancel running task
        running_task.cancel()
        try:
            await running_task
        except asyncio.CancelledError:
            pass
        
        # Stop cleanup
        await runner.stop_periodic_cleanup()
    
    @pytest.mark.asyncio
    async def test_periodic_cleanup_stops_gracefully(self):
        """Test that periodic cleanup stops correctly."""
        runner = make_runner()
        
        # Start periodic cleanup
        runner.start_periodic_cleanup(interval_seconds=0.1)
        
        # Verify it's running
        assert runner._cleanup_running is True
        assert runner._cleanup_task is not None
        assert not runner._cleanup_task.done()
        
        # Wait a bit to ensure it's actually running
        await asyncio.sleep(0.15)
        
        # Stop cleanup
        await runner.stop_periodic_cleanup()
        
        # Give it a moment to fully stop
        await asyncio.sleep(0.1)
        
        # Verify it stopped
        assert runner._cleanup_running is False
        assert runner._cleanup_task is None or runner._cleanup_task.done()
    
    @pytest.mark.asyncio
    async def test_periodic_cleanup_handles_errors(self):
        """Test that periodic cleanup handles errors gracefully."""
        runner = make_runner()
        
        # Mock _cleanup_dead_tasks to raise an error
        original_cleanup = runner._cleanup_dead_tasks
        call_count = 0
        
        async def error_cleanup():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Test error")
            # Second call should succeed
            await original_cleanup()
        
        runner._cleanup_dead_tasks = error_cleanup
        
        # Start periodic cleanup
        runner.start_periodic_cleanup(interval_seconds=0.05)  # Shorter interval for faster test
        
        # Wait for multiple cleanup cycles (error + retry + normal)
        await asyncio.sleep(0.3)
        
        # Verify cleanup continued running despite error
        assert runner._cleanup_running is True
        # Should have been called at least once (the error call)
        # And possibly more if it recovered
        assert call_count >= 1
        
        # Stop cleanup
        await runner.stop_periodic_cleanup()
        
        # Give it a moment to fully stop
        await asyncio.sleep(0.1)
    
    @pytest.mark.asyncio
    async def test_periodic_cleanup_multiple_dead_tasks(self):
        """Test that periodic cleanup handles multiple dead tasks."""
        runner = make_runner()
        
        # Create multiple dead tasks
        dead_tasks = []
        strategy_ids = []
        
        for i in range(3):
            task = asyncio.create_task(asyncio.sleep(0.01))
            await task  # Wait for completion
            
            payload = CreateStrategyRequest(
                name=f"Dead Strategy {i}",
                symbol="BTCUSDT",
                strategy_type=StrategyType.ema_crossover,
                leverage=10,
                risk_per_trade=0.02,
                params=StrategyParams(interval_seconds=60),
                fixed_amount=100.0
            )
            summary = runner.register(payload)
            strategy_id = summary.id
            
            async with runner._lock:
                runner._tasks[strategy_id] = task
                summary.status = StrategyState.running
                runner._strategies[strategy_id] = summary
            
            dead_tasks.append(task)
            strategy_ids.append(strategy_id)
        
        # Verify all tasks are dead
        assert all(task.done() for task in dead_tasks)
        assert all(sid in runner._tasks for sid in strategy_ids)
        
        # Start periodic cleanup
        runner.start_periodic_cleanup(interval_seconds=0.1)
        
        # Wait for cleanup
        await asyncio.sleep(0.25)
        
        # Verify all dead tasks were cleaned up
        assert all(sid not in runner._tasks for sid in strategy_ids)
        assert all(runner._strategies[sid].status == StrategyState.error for sid in strategy_ids)
        
        # Stop cleanup
        await runner.stop_periodic_cleanup()
        
        # Give it a moment to fully stop
        await asyncio.sleep(0.1)
    
    @pytest.mark.asyncio
    async def test_periodic_cleanup_respects_interval(self):
        """Test that periodic cleanup respects the configured interval."""
        runner = make_runner()
        
        cleanup_calls = []
        
        # Track cleanup calls
        original_cleanup = runner._cleanup_dead_tasks
        
        async def tracked_cleanup():
            cleanup_calls.append(datetime.now(timezone.utc))
            await original_cleanup()
        
        runner._cleanup_dead_tasks = tracked_cleanup
        
        # Start with 0.2 second interval
        interval = 0.2
        runner.start_periodic_cleanup(interval_seconds=interval)
        
        # Wait for multiple cleanup cycles
        await asyncio.sleep(0.7)  # Should get at least 3 calls
        
        # Stop cleanup
        await runner.stop_periodic_cleanup()
        
        # Give it a moment to fully stop
        await asyncio.sleep(0.1)
        
        # Verify cleanup was called multiple times
        assert len(cleanup_calls) >= 3
        
        # Verify intervals are approximately correct (allow some variance)
        if len(cleanup_calls) >= 2:
            intervals = [
                (cleanup_calls[i+1] - cleanup_calls[i]).total_seconds()
                for i in range(len(cleanup_calls) - 1)
            ]
            # Each interval should be approximately the configured interval
            # Allow 50% variance for timing issues
            for interval_time in intervals:
                assert interval * 0.5 <= interval_time <= interval * 1.5, \
                    f"Interval {interval_time} not within expected range"
    
    @pytest.mark.asyncio
    async def test_start_periodic_cleanup_idempotent(self):
        """Test that starting periodic cleanup multiple times doesn't create multiple tasks."""
        runner = make_runner()
        
        # Start cleanup multiple times
        runner.start_periodic_cleanup(interval_seconds=0.1)
        task1 = runner._cleanup_task
        
        # Try to start again (should be ignored)
        runner.start_periodic_cleanup(interval_seconds=0.1)
        task2 = runner._cleanup_task
        
        # Should be the same task
        assert task1 is task2
        
        # Stop cleanup
        await runner.stop_periodic_cleanup()
    
    @pytest.mark.asyncio
    async def test_stop_periodic_cleanup_idempotent(self):
        """Test that stopping periodic cleanup multiple times is safe."""
        runner = make_runner()
        
        # Start cleanup
        runner.start_periodic_cleanup(interval_seconds=0.1)
        
        # Stop multiple times (should be safe)
        await runner.stop_periodic_cleanup()
        await runner.stop_periodic_cleanup()
        await runner.stop_periodic_cleanup()
        
        # Should still be stopped
        assert runner._cleanup_running is False

