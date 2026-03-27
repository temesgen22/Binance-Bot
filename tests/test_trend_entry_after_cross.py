"""Trend follow-up after cross (cross_or_trend) — helper and defaults."""

import pytest
from unittest.mock import MagicMock

from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.base import StrategyContext
from app.core.my_binance_client import BinanceClient


def _kl(open_time_ms: int, close: float, close_time_ms: int) -> list:
    return [
        open_time_ms,
        close,
        close,
        close,
        close,
        100.0,
        close_time_ms,
        0,
        0,
        0,
        0,
        0,
    ]


def test_bars_after_regime_arm_counts_from_last_closed():
    t0, t1, t2 = 1000, 2000, 3000
    closed = [_kl(0, 100.0, t0), _kl(60000, 101.0, t1), _kl(120000, 102.0, t2)]
    assert EmaScalpingStrategy._bars_after_regime_arm(closed, t2) == 0
    assert EmaScalpingStrategy._bars_after_regime_arm(closed, t1) == 1
    assert EmaScalpingStrategy._bars_after_regime_arm(closed, t0) == 2


@pytest.fixture
def mock_client():
    c = MagicMock(spec=BinanceClient)
    c.get_price = MagicMock(return_value=100.0)
    c.get_klines = MagicMock(return_value=[])
    return c


def test_default_entry_mode_cross_only(mock_client):
    ctx = StrategyContext(
        id="trend-defaults",
        name="t",
        symbol="BTCUSDT",
        leverage=1,
        risk_per_trade=0.01,
        params={
            "ema_fast": 5,
            "ema_slow": 10,
            "kline_interval": "1m",
            "enable_htf_bias": False,
            "cooldown_candles": 0,
        },
        interval_seconds=10,
    )
    s = EmaScalpingStrategy(ctx, mock_client)
    assert s.entry_mode == "cross_only"
    assert s.trend_entry_max_candles_after_cross == 0
    assert not s.trend_entry_unlimited_after_cross
    assert s.trend_entry_max_per_regime >= 1


def test_trend_window_off_when_max_zero_and_not_unlimited(mock_client):
    ctx = StrategyContext(
        id="trend-window",
        name="t",
        symbol="BTCUSDT",
        leverage=1,
        risk_per_trade=0.01,
        params={
            "ema_fast": 5,
            "ema_slow": 10,
            "kline_interval": "1m",
            "enable_htf_bias": False,
            "cooldown_candles": 0,
            "entry_mode": "cross_or_trend",
            "trend_entry_max_candles_after_cross": 0,
            "trend_entry_unlimited_after_cross": False,
        },
        interval_seconds=10,
    )
    s = EmaScalpingStrategy(ctx, mock_client)
    s._regime_armed_at = 1000
    closed = [_kl(0, 100.0, 1000), _kl(60000, 101.0, 2000)]
    assert not s._trend_followup_window_ok_scalping(closed)
