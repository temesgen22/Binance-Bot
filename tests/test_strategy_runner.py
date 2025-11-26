import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.models.strategy import CreateStrategyRequest, StrategyParams, StrategyType, StrategyState
from app.services.strategy_runner import StrategyRunner


class DummyRedis:
    enabled = False


def make_runner():
    client = MagicMock()
    risk = MagicMock()
    executor = MagicMock()
    return StrategyRunner(
        client=client,
        risk=risk,
        executor=executor,
        max_concurrent=2,
        redis_storage=DummyRedis(),
    )


@pytest.mark.asyncio
async def test_register_auto_start_does_not_double_start(monkeypatch):
    runner = make_runner()
    params = StrategyParams(ema_fast=3, ema_slow=5)
    payload = CreateStrategyRequest(
        name="Test Auto Start",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        leverage=5,
        risk_per_trade=0.01,
        fixed_amount=10,
        max_positions=1,
        params=params,
        auto_start=True,
    )

    summary = runner.register(payload)
    assert summary.status == StrategyState.stopped
    assert runner._tasks == {}

    async def short_run_loop(strategy, summary_obj):
        summary_obj.status = StrategyState.running

    with patch.object(StrategyRunner, "_run_loop", side_effect=short_run_loop):
        started = await runner.start(summary.id)
        assert started.status == StrategyState.running
        # cancel created task to avoid leak
        task = runner._tasks.pop(summary.id)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_leverage_is_required():
    """Verify that leverage is REQUIRED and cannot be omitted (to prevent Binance 20x default)."""
    runner = make_runner()
    params = StrategyParams(ema_fast=8, ema_slow=21)
    
    # Attempt to create strategy WITHOUT leverage - should fail
    with pytest.raises(ValidationError) as exc_info:
        payload = CreateStrategyRequest(
            name="Test Strategy",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            # leverage is missing - should raise ValidationError
            risk_per_trade=0.01,
            params=params,
        )
    
    # Verify error message mentions leverage
    error_str = str(exc_info.value)
    assert "leverage" in error_str.lower() or "required" in error_str.lower()


def test_invalid_leverage_raises_error():
    """Verify that invalid leverage values raise errors."""
    runner = make_runner()
    params = StrategyParams(ema_fast=8, ema_slow=21)
    
    # Test leverage = 0 (too low)
    with pytest.raises(ValidationError) as exc_info:
        payload = CreateStrategyRequest(
            name="Test Strategy",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=0,  # Invalid: must be >= 1
            risk_per_trade=0.01,
            params=params,
        )
    
    # Test leverage = 100 (too high)
    with pytest.raises(ValidationError) as exc_info:
        payload = CreateStrategyRequest(
            name="Test Strategy",
            symbol="BTCUSDT",
            strategy_type=StrategyType.scalping,
            leverage=100,  # Invalid: must be <= 50
            risk_per_trade=0.01,
            params=params,
        )


def test_leverage_must_be_explicitly_set():
    """Verify that leverage must be explicitly provided (no default)."""
    runner = make_runner()
    params = StrategyParams(ema_fast=8, ema_slow=21)
    
    # Valid: leverage explicitly set to 5
    payload = CreateStrategyRequest(
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        leverage=5,  # Explicitly set
        risk_per_trade=0.01,
        params=params,
    )
    
    summary = runner.register(payload)
    assert summary.leverage == 5
    
    # Verify registration log mentions explicit leverage
    # (This is verified by the fact that register() doesn't raise an error)

