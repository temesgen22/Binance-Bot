import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from uuid import uuid4

from app.models.strategy import CreateStrategyRequest, StrategyParams, StrategyType, StrategyState, StrategySummary
from app.services.strategy_runner import StrategyRunner
from app.services.strategy_executor import StrategyExecutor
from app.core.binance_client_manager import BinanceClientManager
from app.core.config import get_settings


class DummyRedis:
    enabled = False


def make_runner():
    """Create a StrategyRunner for testing (backward compatible)."""
    client = MagicMock()
    risk = MagicMock()
    executor = MagicMock()
    
    # Create a minimal client manager for backward compatibility
    # The StrategyRunner will create one automatically if not provided,
    # Accounts are loaded from database, not .env
    settings = get_settings()
    manager = BinanceClientManager(settings)
    
    # Manually add default account (simulating database-loaded account)
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
        use_websocket=False,  # Disable WebSocket in tests
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

    async def short_run_loop(strategy, summary_obj, risk=None, executor=None):
        summary_obj.status = StrategyState.running
        # Wait a bit so the task doesn't complete immediately (which triggers error detection)
        await asyncio.sleep(0.2)

    with patch.object(StrategyExecutor, "run_loop", side_effect=short_run_loop):
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


@pytest.mark.asyncio
async def test_stop_closes_only_when_strategy_owned():
    """Stop closes position only when strategy owns it (position_instance_id + entry trades); else leaves position as is."""
    from datetime import datetime, timezone

    runner = make_runner()
    strategy_uuid = uuid4()
    summary = StrategySummary(
        id=str(strategy_uuid),
        name="Owned",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=5,
        risk_per_trade=0.02,
        fixed_amount=None,
        params=StrategyParams(),
        account_id="default",
        created_at=datetime.now(timezone.utc),
        last_signal=None,
    )
    runner._strategies[str(strategy_uuid)] = summary
    mock_task = AsyncMock()
    mock_task.done = MagicMock(return_value=False)
    mock_task.cancel = MagicMock()
    runner._tasks[str(strategy_uuid)] = mock_task

    mock_client = MagicMock()
    runner._get_account_client = MagicMock(return_value=mock_client)
    mock_client.get_open_position = MagicMock(return_value={
        "positionAmt": "0.001",
        "entryPrice": "40000.0",
        "unRealizedProfit": "0",
        "markPrice": "40000.0",
    })
    mock_client.close_position = MagicMock()
    mock_client.place_order = MagicMock(return_value=MagicMock(
        side="SELL",
        symbol="BTCUSDT",
        executed_qty=0.001,
        avg_price=40000.0,
        price=40000.0,
        order_id=12345,
        status="FILLED",
    ))
    runner.order_manager = MagicMock()
    runner.order_manager.cancel_tp_sl_orders = AsyncMock()

    db_strategy = MagicMock()
    db_strategy.id = strategy_uuid
    db_strategy.position_instance_id = uuid4()
    strategy_service = MagicMock()
    strategy_service.db_service.get_strategy_by_uuid = MagicMock(return_value=db_strategy)
    strategy_service.db_service.get_strategy_owned_quantity = MagicMock(return_value=(0.001, True))
    runner.strategy_service = strategy_service
    runner.trade_service = MagicMock()
    runner.user_id = uuid4()

    await runner.stop(str(strategy_uuid))

    # Should close only via place_order (strategy-owned qty), not close_position
    assert mock_client.place_order.call_count == 1
    call_kw = mock_client.place_order.call_args.kwargs
    assert call_kw.get("reduce_only") is True
    assert call_kw.get("quantity") == 0.001
    assert call_kw.get("side") == "SELL"
    assert mock_client.close_position.call_count == 0

