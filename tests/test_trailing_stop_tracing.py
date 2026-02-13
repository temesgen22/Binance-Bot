"""End-to-end tests for trailing stop activity tracing (record_trail_update wiring)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.strategies.trailing_stop import TrailUpdateEvent, TrailingStopManager
from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.base import StrategyContext


def test_trailing_stop_update_returns_event_when_levels_change_long():
    """TrailingStopManager.update() returns TrailUpdateEvent when TP/SL are updated (LONG)."""
    manager = TrailingStopManager(
        entry_price=100.0,
        take_profit_pct=0.005,
        stop_loss_pct=0.003,
        position_type="LONG",
        enabled=True,
        activation_pct=0.0,
    )
    tp, sl, event = manager.update(100.0)
    assert event is None  # No change at entry
    tp, sl, event = manager.update(101.0)  # New best price
    assert event is not None
    assert isinstance(event, TrailUpdateEvent)
    assert event.best_price == 101.0
    assert event.position_side == "LONG"
    assert event.tp_price == 101.0 * 1.005
    assert event.sl_price == 101.0 * 0.997
    # Same price again -> no new event
    tp, sl, event2 = manager.update(101.0)
    assert event2 is None


def test_trailing_stop_update_returns_event_when_levels_change_short():
    """TrailingStopManager.update() returns TrailUpdateEvent when TP/SL are updated (SHORT)."""
    manager = TrailingStopManager(
        entry_price=100.0,
        take_profit_pct=0.005,
        stop_loss_pct=0.003,
        position_type="SHORT",
        enabled=True,
        activation_pct=0.0,
    )
    tp, sl, event = manager.update(99.0)  # New best (low) price
    assert event is not None
    assert event.best_price == 99.0
    assert event.position_side == "SHORT"


@pytest.mark.asyncio
async def test_scalping_calls_trail_recorder_when_trail_event_emitted():
    """When trail_recorder is set and trailing stop emits an event, record_trail_update is called."""
    context = StrategyContext(
        id="trace-test-1",
        name="Trace Test",
        symbol="BTCUSDT",
        leverage=5,
        risk_per_trade=0.01,
        params={
            "ema_fast": 3,
            "ema_slow": 5,
            "kline_interval": "1m",
            "take_profit_pct": 0.004,
            "stop_loss_pct": 0.002,
            "trailing_stop_enabled": True,
            "trailing_stop_activation_pct": 0.0,
            "enable_short": False,
        },
        interval_seconds=60,
    )
    client = MagicMock()
    strategy = EmaScalpingStrategy(context, client)
    strategy.position = "LONG"
    strategy.entry_price = 100.0
    strategy.trailing_stop = TrailingStopManager(
        entry_price=100.0,
        take_profit_pct=0.005,
        stop_loss_pct=0.003,
        position_type="LONG",
        enabled=True,
        activation_pct=0.0,
    )
    recorder = MagicMock()
    strategy.set_trail_recorder(recorder)

    # Trigger a trail update (price 101 > 100)
    signal = strategy._check_tp_sl(101.0)

    recorder.record_trail_update.assert_called_once()
    call = recorder.record_trail_update.call_args
    assert call[0][0] == "trace-test-1"  # strategy_id
    assert call[0][1] == "BTCUSDT"  # symbol
    assert call[0][2] == "LONG"  # position_side
    assert call[0][3] == 101.0  # best_price
    assert call[0][4] == 101.0 * 1.005  # tp_price
    assert call[0][5] == 101.0 * 0.997  # sl_price
    # No exit at 101
    assert signal is None


@pytest.mark.asyncio
async def test_scalping_does_not_call_recorder_when_no_recorder_set():
    """When trail_recorder is not set, record_trail_update is never called."""
    context = StrategyContext(
        id="trace-test-2",
        name="Trace Test",
        symbol="BTCUSDT",
        leverage=5,
        risk_per_trade=0.01,
        params={
            "ema_fast": 3,
            "ema_slow": 5,
            "kline_interval": "1m",
            "take_profit_pct": 0.004,
            "stop_loss_pct": 0.002,
            "trailing_stop_enabled": True,
            "trailing_stop_activation_pct": 0.0,
            "enable_short": False,
        },
        interval_seconds=60,
    )
    client = MagicMock()
    strategy = EmaScalpingStrategy(context, client)
    strategy.position = "LONG"
    strategy.entry_price = 100.0
    strategy.trailing_stop = TrailingStopManager(
        entry_price=100.0,
        take_profit_pct=0.005,
        stop_loss_pct=0.003,
        position_type="LONG",
        enabled=True,
        activation_pct=0.0,
    )
    # Do NOT set trail_recorder (e.g. backtest)
    strategy._check_tp_sl(101.0)
    # No recorder to call; no exception
    assert getattr(strategy, "trail_recorder", None) is None
