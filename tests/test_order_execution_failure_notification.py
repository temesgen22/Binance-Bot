"""
Tests for order execution failure notification and strategy state details.

Validates that when an order is not executed (timeout, API error, insufficient balance, etc.):
1. Strategy meta is updated with last_order_failure_reason, last_order_failure_time, last_order_failure_error_type
2. Push notification (notify_order_execution_failed) is sent with the reason
3. Strategy health API returns order_failure block for UI/state details
4. Reason normalization produces user-friendly messages for known errors
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.models.strategy import StrategySummary, StrategyState, StrategyParams, StrategyType
from app.strategies.base import StrategySignal
from app.services.strategy_executor import StrategyExecutor


# --- Unit tests: reason normalization -----------------------------------------


class TestNormalizeOrderFailureReason:
    """Test _normalize_order_failure_reason produces user-friendly messages."""

    def test_insufficient_balance_message(self):
        reason = StrategyExecutor._normalize_order_failure_reason(
            Exception("Margin is insufficient for this order")
        )
        assert "Insufficient balance or margin" in reason or "insufficient" in reason.lower()

    def test_redis_storage_attribute_error(self):
        reason = StrategyExecutor._normalize_order_failure_reason(
            AttributeError("'RedisStorage' object has no attribute 'get'")
        )
        assert "Service error" in reason or "cache" in reason.lower()

    def test_reduce_only_rejected(self):
        reason = StrategyExecutor._normalize_order_failure_reason(
            Exception("ReduceOnly Order is rejected")
        )
        assert "Position already closed" in reason or "rejected" in reason.lower()

    def test_timeout(self):
        reason = StrategyExecutor._normalize_order_failure_reason(
            Exception("Order execution timed out after 60 seconds")
        )
        assert "timed out" in reason or "timeout" in reason.lower()

    def test_binance_error_code_2019(self):
        err = Exception("API Error -2019: Margin is insufficient")
        reason = StrategyExecutor._normalize_order_failure_reason(err)
        assert "Insufficient balance or margin" in reason

    def test_binance_error_code_2022(self):
        err = Exception("API Error -2022: ReduceOnly order is rejected")
        reason = StrategyExecutor._normalize_order_failure_reason(err)
        assert "Position already closed" in reason or "rejected" in reason.lower()

    def test_generic_exception_returns_truncated_message(self):
        reason = StrategyExecutor._normalize_order_failure_reason(
            ValueError("Some custom error here")
        )
        assert "Some custom error here" in reason

    def test_empty_exception_returns_type_name(self):
        reason = StrategyExecutor._normalize_order_failure_reason(TimeoutError())
        assert "Timeout" in reason or "timeout" in reason.lower() or reason == "TimeoutError"


# --- Integration: meta + notification on order failure ------------------------


def _make_summary():
    return StrategySummary(
        id="test-strategy-123",
        name="Test Strategy",
        symbol="BTCUSDT",
        strategy_type=StrategyType.scalping,
        status=StrategyState.running,
        leverage=10,
        risk_per_trade=0.01,
        account_id="default",
        params=StrategyParams(interval_seconds=60),
        created_at=datetime.now(timezone.utc),
        last_signal="HOLD",
        meta={},
    )


@pytest.fixture
def mock_account_manager():
    m = MagicMock()
    m.get_account_client.return_value = MagicMock()
    return m


@pytest.fixture
def mock_state_manager():
    m = MagicMock()
    m.update_strategy_in_db = MagicMock(return_value=True)
    return m


@pytest.fixture
def mock_order_manager():
    m = MagicMock()
    m.user_id = uuid4()
    return m


@pytest.fixture
def mock_client_manager():
    m = MagicMock()
    m.get_account_config.return_value = MagicMock(name="Default")
    return m


@pytest.fixture
def mock_notifications():
    m = MagicMock()
    m.notify_order_execution_failed = AsyncMock()
    m.notify_strategy_stopped = AsyncMock()  # run_loop calls this on CancelledError
    return m


@pytest.fixture
def executor(
    mock_account_manager,
    mock_state_manager,
    mock_order_manager,
    mock_client_manager,
    mock_notifications,
):
    return StrategyExecutor(
        account_manager=mock_account_manager,
        state_manager=mock_state_manager,
        order_manager=mock_order_manager,
        client_manager=mock_client_manager,
        notification_service=mock_notifications,
    )


@pytest.mark.asyncio
async def test_order_execution_exception_updates_meta_and_calls_notify(
    executor,
    mock_state_manager,
    mock_notifications,
):
    """When _execute_order raises, meta is updated and notify_order_execution_failed is called."""
    summary = _make_summary()
    signal = StrategySignal(action="BUY", symbol="BTCUSDT", confidence=0.8, price=50000.0)

    async def fake_evaluate():
        return signal

    async def failing_execute_order(*args, **kwargs):
        raise Exception("Insufficient balance for this trade")

    async def cancel_after_wait(*args, **kwargs):
        raise asyncio.CancelledError()

    strategy = MagicMock()
    strategy.evaluate = AsyncMock(side_effect=fake_evaluate)
    strategy.sync_position_state = MagicMock()
    strategy.teardown = AsyncMock()

    with (
        patch.object(executor, "_execute_order", failing_execute_order),
        patch.object(executor, "_wait_for_next_evaluation", cancel_after_wait),
    ):
        with pytest.raises(asyncio.CancelledError):
            await executor.run_loop(strategy, summary)

    assert isinstance(summary.meta, dict)
    assert "last_order_failure_reason" in summary.meta
    assert "last_order_failure_time" in summary.meta
    assert "last_order_failure_error_type" in summary.meta
    assert summary.meta["last_order_failure_error_type"] == "Exception"
    assert "Insufficient balance" in summary.meta["last_order_failure_reason"] or "insufficient" in summary.meta["last_order_failure_reason"].lower()

    mock_notifications.notify_order_execution_failed.assert_called_once()
    call_args, call_kw = mock_notifications.notify_order_execution_failed.call_args
    assert call_args[0] == summary
    assert call_args[1] == summary.meta["last_order_failure_reason"]
    assert call_kw["error_type"] == "Exception"
    assert call_kw["signal_action"] == "BUY"
    assert call_kw["symbol"] == "BTCUSDT"
    assert call_kw["user_id"] == executor.order_manager.user_id

    assert mock_state_manager.update_strategy_in_db.called
    for call in mock_state_manager.update_strategy_in_db.call_args_list:
        call_meta = call[1].get("meta")
        if call_meta and call_meta.get("last_order_failure_reason"):
            assert call_meta.get("last_order_failure_reason") == summary.meta["last_order_failure_reason"]
            break
    else:
        assert summary.meta.get("last_order_failure_reason")


@pytest.mark.asyncio
async def test_order_execution_timeout_updates_meta_and_calls_notify(
    executor,
    mock_state_manager,
    mock_notifications,
):
    """When order execution times out, meta has TimeoutError reason and notify is called."""
    summary = _make_summary()
    signal = StrategySignal(action="SELL", symbol="ETHUSDT", confidence=0.9, price=3000.0)

    async def fake_evaluate():
        return signal

    async def raise_timeout(*args, **kwargs):
        raise asyncio.TimeoutError("Order execution timed out")

    async def cancel_after_wait(*args, **kwargs):
        raise asyncio.CancelledError()

    strategy = MagicMock()
    strategy.evaluate = AsyncMock(side_effect=fake_evaluate)
    strategy.sync_position_state = MagicMock()
    strategy.teardown = AsyncMock()

    with (
        patch.object(executor, "_execute_order", raise_timeout),
        patch.object(executor, "_wait_for_next_evaluation", cancel_after_wait),
    ):
        with pytest.raises(asyncio.CancelledError):
            await executor.run_loop(strategy, summary)

    assert isinstance(summary.meta, dict)
    assert summary.meta.get("last_order_failure_reason") == "Order execution timed out"
    assert summary.meta.get("last_order_failure_error_type") == "TimeoutError"
    assert "last_order_failure_time" in summary.meta
    assert "last_order_timeout" in summary.meta

    mock_notifications.notify_order_execution_failed.assert_called_once()
    call_args, call_kw = mock_notifications.notify_order_execution_failed.call_args
    assert call_args[1] == "Order execution timed out"
    assert call_kw["error_type"] == "TimeoutError"
    assert call_kw["signal_action"] == "SELL"


# --- API: strategy health returns order_failure ---------------------------------


@pytest.mark.asyncio
async def test_strategy_health_returns_order_failure_when_meta_has_reason():
    """GET /strategies/{id}/health returns order_failure block when meta has last_order_failure_reason."""
    from app.api.routes.strategies import get_strategy_health
    from app.models.db_models import User
    from sqlalchemy.orm import Session

    strategy_id = "health-test-strategy"
    user = MagicMock(spec=User)
    user.id = uuid4()

    mock_runner = MagicMock()
    mock_strategy = _make_summary()
    mock_strategy.id = strategy_id
    mock_strategy.name = "Health Test"
    mock_strategy.meta = {
        "last_order_failure_reason": "Insufficient balance or margin",
        "last_order_failure_time": "2026-02-28T20:00:00+00:00",
        "last_order_failure_error_type": "AttributeError",
        "orders_executed_count": 5,
        "orders_skipped_count": 2,
    }
    mock_strategy.status = StrategyState.running
    mock_strategy.started_at = datetime.now(timezone.utc)
    mock_runner.list_strategies.return_value = [mock_strategy]
    mock_runner._tasks = {strategy_id: MagicMock(done=MagicMock(return_value=False))}

    mock_db = MagicMock(spec=Session)
    mock_db_instance = MagicMock()
    mock_db_instance.get_strategy.return_value = MagicMock(id=uuid4())
    mock_trade_instance = MagicMock()
    mock_trade_instance.get_strategy_trades.return_value = []

    MockDB = MagicMock(return_value=mock_db_instance)
    MockTrade = MagicMock(return_value=mock_trade_instance)
    with (
        patch("app.services.database_service.DatabaseService", MockDB),
        patch("app.services.trade_service.TradeService", MockTrade),
    ):
        result = await get_strategy_health(
            strategy_id=strategy_id,
            current_user=user,
            runner=mock_runner,
            db=mock_db,
        )

    assert "order_failure" in result
    assert result["order_failure"] is not None
    assert result["order_failure"]["reason"] == "Insufficient balance or margin"
    assert result["order_failure"]["at"] == "2026-02-28T20:00:00+00:00"
    assert result["order_failure"]["error_type"] == "AttributeError"


@pytest.mark.asyncio
async def test_strategy_health_order_failure_null_when_no_failure_in_meta():
    """GET /strategies/{id}/health returns order_failure: null when meta has no failure reason."""
    from app.api.routes.strategies import get_strategy_health
    from app.models.db_models import User

    strategy_id = "no-failure-strategy"
    user = MagicMock(spec=User)
    user.id = uuid4()

    mock_runner = MagicMock()
    mock_strategy = _make_summary()
    mock_strategy.id = strategy_id
    mock_strategy.name = "No Failure"
    mock_strategy.meta = {"orders_executed_count": 10, "orders_skipped_count": 0}
    mock_strategy.status = StrategyState.running
    mock_strategy.started_at = datetime.now(timezone.utc)
    mock_runner.list_strategies.return_value = [mock_strategy]
    mock_runner._tasks = {strategy_id: MagicMock(done=MagicMock(return_value=False))}

    mock_db = MagicMock()
    mock_db_instance = MagicMock()
    mock_db_instance.get_strategy.return_value = MagicMock(id=uuid4())
    mock_trade_instance = MagicMock()
    mock_trade_instance.get_strategy_trades.return_value = []

    MockDB = MagicMock(return_value=mock_db_instance)
    MockTrade = MagicMock(return_value=mock_trade_instance)
    with (
        patch("app.services.database_service.DatabaseService", MockDB),
        patch("app.services.trade_service.TradeService", MockTrade),
    ):
        result = await get_strategy_health(
            strategy_id=strategy_id,
            current_user=user,
            runner=mock_runner,
            db=mock_db,
        )

    assert "order_failure" in result
    assert result["order_failure"] is None
