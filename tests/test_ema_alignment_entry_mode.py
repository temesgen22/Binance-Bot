"""EMA alignment entry mode: enter on fast/slow alignment without cross."""

import pytest
from unittest.mock import MagicMock

from app.strategies.scalping import EmaScalpingStrategy
from app.strategies.reverse_scalping import ReverseScalpingStrategy
from app.strategies.base import StrategyContext
from app.core.my_binance_client import BinanceClient


def _k(open_time_ms: int, close: float, close_time_ms: int) -> list:
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


def _build_rising_klines(
    n_closed: int, start_ct: int = 1_000_000, step_ms: int = 60_000, start_price: float = 100.0
) -> list:
    """Strictly rising closes so fast EMA > slow EMA on last closed bar (no golden cross that bar)."""
    out = []
    for i in range(n_closed):
        ct = start_ct + i * step_ms
        c = start_price + float(i) * 0.5
        out.append(_k(ct - step_ms, c, ct))
    last_close = start_price + (n_closed - 1) * 0.5
    out.append(_k(start_ct + n_closed * step_ms - step_ms, last_close, start_ct + n_closed * step_ms))
    return out


@pytest.fixture
def mock_client():
    c = MagicMock(spec=BinanceClient)
    c.get_price = MagicMock(return_value=125.0)
    c.get_klines = MagicMock(return_value=[])
    c.get_open_position = MagicMock(return_value=None)
    return c


def test_entry_mode_parses_ema_alignment(mock_client):
    ctx = StrategyContext(
        id="ea-parse",
        name="t",
        symbol="BTCUSDT",
        leverage=1,
        risk_per_trade=0.01,
        params={
            "ema_fast": 3,
            "ema_slow": 5,
            "kline_interval": "1m",
            "enable_htf_bias": False,
            "cooldown_candles": 0,
            "entry_mode": "ema_alignment",
            "min_ema_separation": 1e-9,
        },
        interval_seconds=10,
    )
    s = EmaScalpingStrategy(ctx, mock_client)
    assert s.entry_mode == "ema_alignment"


def test_unknown_entry_mode_falls_back_cross_only(mock_client):
    ctx = StrategyContext(
        id="ea-bad",
        name="t",
        symbol="BTCUSDT",
        leverage=1,
        risk_per_trade=0.01,
        params={"ema_fast": 3, "ema_slow": 5, "kline_interval": "1m", "entry_mode": "nope"},
        interval_seconds=10,
    )
    s = EmaScalpingStrategy(ctx, mock_client)
    assert s.entry_mode == "cross_only"


@pytest.mark.asyncio
async def test_ema_alignment_scalping_long_without_cross(mock_client):
    klines = _build_rising_klines(45)
    mock_client.get_klines = MagicMock(return_value=klines)

    ctx = StrategyContext(
        id="ea-long",
        name="t",
        symbol="BTCUSDT",
        leverage=1,
        risk_per_trade=0.01,
        params={
            "ema_fast": 3,
            "ema_slow": 5,
            "kline_interval": "1m",
            "enable_htf_bias": False,
            "cooldown_candles": 0,
            "entry_mode": "ema_alignment",
            "min_ema_separation": 1e-9,
        },
        interval_seconds=10,
    )
    s = EmaScalpingStrategy(ctx, mock_client)
    sig = await s.evaluate()
    assert sig.action == "BUY"
    assert sig.position_side == "LONG"


@pytest.mark.asyncio
async def test_ema_alignment_scalping_cross_only_holds_without_cross(mock_client):
    klines = _build_rising_klines(45)
    mock_client.get_klines = MagicMock(return_value=klines)

    ctx = StrategyContext(
        id="ea-co",
        name="t",
        symbol="BTCUSDT",
        leverage=1,
        risk_per_trade=0.01,
        params={
            "ema_fast": 3,
            "ema_slow": 5,
            "kline_interval": "1m",
            "enable_htf_bias": False,
            "cooldown_candles": 0,
            "entry_mode": "cross_only",
            "min_ema_separation": 1e-9,
        },
        interval_seconds=10,
    )
    s = EmaScalpingStrategy(ctx, mock_client)
    sig = await s.evaluate()
    assert sig.action == "HOLD"


@pytest.mark.asyncio
async def test_ema_alignment_reverse_short_when_fast_above_slow(mock_client):
    klines = _build_rising_klines(45)
    mock_client.get_klines = MagicMock(return_value=klines)

    ctx = StrategyContext(
        id="ea-rev",
        name="t",
        symbol="BTCUSDT",
        leverage=1,
        risk_per_trade=0.01,
        params={
            "ema_fast": 3,
            "ema_slow": 5,
            "kline_interval": "1m",
            "enable_htf_bias": False,
            "cooldown_candles": 0,
            "entry_mode": "ema_alignment",
            "min_ema_separation": 1e-9,
            "enable_short": True,
        },
        interval_seconds=10,
    )
    s = ReverseScalpingStrategy(ctx, mock_client)
    sig = await s.evaluate()
    assert sig.action == "SELL"
    assert sig.position_side == "SHORT"


@pytest.mark.asyncio
async def test_ema_alignment_does_not_arm_regime(mock_client):
    klines = _build_rising_klines(45)
    mock_client.get_klines = MagicMock(return_value=klines)

    ctx = StrategyContext(
        id="ea-noreg",
        name="t",
        symbol="BTCUSDT",
        leverage=1,
        risk_per_trade=0.01,
        params={
            "ema_fast": 3,
            "ema_slow": 5,
            "kline_interval": "1m",
            "enable_htf_bias": False,
            "cooldown_candles": 0,
            "entry_mode": "ema_alignment",
            "min_ema_separation": 1e-9,
        },
        interval_seconds=10,
    )
    s = EmaScalpingStrategy(ctx, mock_client)
    await s.evaluate()
    assert s._entry_regime == "none"
    assert s._regime_armed_at is None
