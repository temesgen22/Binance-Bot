"""Tests for open PnL giveback stop (peak unrealized drawdown in USDT)."""

from unittest.mock import MagicMock

from app.core.my_binance_client import BinanceClient
from app.strategies.base import StrategyContext
from app.strategies.pnl_giveback import giveback_should_trigger, update_peak_unrealized
from app.strategies.scalping import EmaScalpingStrategy


def test_update_peak_monotonic() -> None:
    assert update_peak_unrealized(None, 10.0) == 10.0
    assert update_peak_unrealized(15.0, 12.0) == 15.0
    assert update_peak_unrealized(15.0, 20.0) == 20.0


def test_giveback_trigger_threshold() -> None:
    ok, _ = giveback_should_trigger(
        peak_unrealized=100.0,
        current_unrealized=92.0,
        min_peak_usdt=50.0,
        giveback_usdt=5.0,
    )
    assert ok is True

    ok2, _ = giveback_should_trigger(
        peak_unrealized=100.0,
        current_unrealized=96.0,
        min_peak_usdt=50.0,
        giveback_usdt=5.0,
    )
    assert ok2 is False


def test_giveback_respects_min_peak() -> None:
    ok, _ = giveback_should_trigger(
        peak_unrealized=8.0,
        current_unrealized=0.0,
        min_peak_usdt=10.0,
        giveback_usdt=5.0,
    )
    assert ok is False


def test_scalping_pnl_giveback_exit_emits_close() -> None:
    ctx = StrategyContext(
        id="gb-test",
        name="gb-test",
        symbol="BTCUSDT",
        leverage=5,
        risk_per_trade=0.01,
        params={
            "ema_fast": 8,
            "ema_slow": 21,
            "take_profit_pct": 0.004,
            "stop_loss_pct": 0.002,
            "kline_interval": "1m",
            "interval_seconds": 10,
            "pnl_giveback_enabled": True,
            "pnl_giveback_from_peak_usdt": 10.0,
            "pnl_giveback_min_peak_usdt": 5.0,
        },
        interval_seconds=10,
    )
    client = MagicMock(spec=BinanceClient)
    s = EmaScalpingStrategy(ctx, client)
    s.position = "LONG"
    s.entry_price = 100.0
    s.entry_candle_time = None
    s.last_closed_candle_time = 1
    s.peak_unrealized_pnl = 100.0  # Simulate prior favorable excursion before this tick
    sig = s._maybe_pnl_giveback_exit(101.0, 85.0, "")
    assert sig is not None
    assert sig.action == "SELL"
    assert sig.exit_reason == "PNL_GIVEBACK"
    assert s.position is None
