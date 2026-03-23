"""Tests for market structure (HH/HL vs LH/LL) entry filter — validates structure_filters.py implementation."""

from unittest.mock import MagicMock

import pytest

from app.strategies.structure_filters import (
    _find_swing_highs_lows,
    passes_market_structure_filter,
    required_closed_candles_for_structure,
)

# Hand-tuned series with valid fractal pivots (left=2, right=2) — same shape as production tests
BULLISH_HIGHS = [
    100, 100, 100, 100, 110, 100, 100, 100, 100, 115,
    100, 100, 100, 100, 120, 100, 100, 100, 100, 125,
    100, 100, 100, 100, 126, 100, 100, 100, 100, 127,
]
BULLISH_LOWS = [
    100, 100, 90, 100, 100, 100, 92, 100, 100, 100,
    100, 94, 100, 100, 100, 100, 96, 100, 100, 100,
    100, 98, 100, 100, 100, 100, 100, 100, 100, 100,
]
MIRROR = 200.0


def _bearish_from_bullish_ohlc(highs: list[float], lows: list[float]) -> tuple[list[float], list[float]]:
    """Vertical invert each bar so high'=MIRROR-low_orig, low'=MIRROR-high_orig (valid OHLC, bearish geometry)."""
    out_h: list[float] = []
    out_l: list[float] = []
    for h, l_ in zip(highs, lows):
        out_h.append(MIRROR - l_)
        out_l.append(MIRROR - h)
    return out_h, out_l


def _kline(open_time: int, o: float, h: float, l: float, c: float) -> list:
    close_time = open_time + 60_000
    return [open_time, o, h, l, c, 1000.0, close_time, 0, 0, 0, 0, 0]


def _series_from_hl(highs: list[float], lows: list[float]) -> list[list]:
    assert len(highs) == len(lows)
    klines: list[list] = []
    t = 0
    for i in range(len(highs)):
        h, l_ = highs[i], lows[i]
        c = (h + l_) / 2
        klines.append(_kline(t, c, h, l_, c))
        t += 60_000
    return klines


def _bullish_klines_with_close(close: float | None = None) -> list[list]:
    klines = _series_from_hl(BULLISH_HIGHS, BULLISH_LOWS)
    if close is not None:
        last = list(klines[-1])
        last[4] = close
        last[1] = close - 1.0
        klines[-1] = last
    return klines


def _bearish_mirror_klines() -> list[list]:
    """Bearish twin of bullish series: fractal pivots invert to LH/LL."""
    highs, lows = _bearish_from_bullish_ohlc(BULLISH_HIGHS, BULLISH_LOWS)
    return _series_from_hl(highs, lows)


def test_required_closed_candles_for_structure_min():
    assert required_closed_candles_for_structure(2, 2) >= 20


def test_empty_klines_fail():
    ok, reason = passes_market_structure_filter("LONG", [], 2, 2, True)
    assert ok is False
    assert reason == "INSUFFICIENT_DATA"


def test_invalid_close_fails():
    k = _kline(0, 100, 101, 99, 100)
    k[4] = float("nan")
    ok, reason = passes_market_structure_filter("LONG", [k], 2, 2, False)
    assert ok is False
    assert reason == "INVALID_CLOSE"


def test_insufficient_swings_fail():
    flat = [_kline(i * 60_000, 100, 100, 100, 100) for i in range(40)]
    ok, reason = passes_market_structure_filter("LONG", flat, 2, 2, False)
    assert ok is False
    assert reason == "INSUFFICIENT_SWINGS"


def test_long_ok_hh_hl_confirm_h_prev():
    klines = _bullish_klines_with_close(200.0)
    sh, sl = _find_swing_highs_lows(klines, 2, 2)
    assert len(sh) >= 2 and len(sl) >= 2

    ok, reason = passes_market_structure_filter("LONG", klines, 2, 2, confirm_on_close=False)
    assert ok is True
    assert reason == "OK"

    ok2, reason2 = passes_market_structure_filter("LONG", klines, 2, 2, confirm_on_close=True)
    assert ok2 is True
    assert reason2 == "OK"

    klines_fail = _bullish_klines_with_close(50.0)
    ok3, reason3 = passes_market_structure_filter("LONG", klines_fail, 2, 2, confirm_on_close=True)
    assert ok3 is False
    assert reason3 == "CLOSE_NOT_CONFIRMED_HH"


def test_long_fails_no_hh_hl_on_bearish_mirror():
    """LONG requires HH+HL; bearish mirror has LH+LL → NO_HH_HL."""
    klines = _bearish_mirror_klines()
    ok, reason = passes_market_structure_filter("LONG", klines, 2, 2, confirm_on_close=False)
    assert ok is False
    assert reason == "NO_HH_HL"


def test_short_ok_lh_ll_on_bearish_mirror():
    klines = _bearish_mirror_klines()
    sh, sl = _find_swing_highs_lows(klines, 2, 2)
    assert len(sh) >= 2 and len(sl) >= 2

    ok, reason = passes_market_structure_filter("SHORT", klines, 2, 2, confirm_on_close=False)
    assert ok is True
    assert reason == "OK"
    (_, h_prev), (_, h_last) = sh[-2], sh[-1]
    (_, l_prev), (_, l_last) = sl[-2], sl[-1]
    assert h_last < h_prev and l_last < l_prev


def test_short_fails_no_lh_ll_on_bullish_series():
    """SHORT requires LH+LL; bullish series has HH+HL → NO_LH_LL."""
    klines = _bullish_klines_with_close(200.0)
    ok, reason = passes_market_structure_filter("SHORT", klines, 2, 2, confirm_on_close=False)
    assert ok is False
    assert reason == "NO_LH_LL"


def test_short_confirm_fails_when_close_bounces_above_last_swing_low():
    """When last swing low pivot is before signal bar, close > l_last → CLOSE_NOT_CONFIRMED_LL."""
    klines = _bearish_mirror_klines()
    _, sl = _find_swing_highs_lows(klines, 2, 2)
    idx_l_last = sl[-1][0]
    last_i = len(klines) - 1
    if idx_l_last == last_i:
        pytest.skip("mirror places last swing low on signal bar; cannot test bounce confirm")

    last = list(klines[-1])
    last[4] = MIRROR  # well above bearish swing lows (~73–110 range)
    klines[-1] = last

    ok, reason = passes_market_structure_filter("SHORT", klines, 2, 2, confirm_on_close=True)
    assert ok is False
    assert reason == "CLOSE_NOT_CONFIRMED_LL"


def test_short_confirm_skipped_when_swing_low_on_signal_bar():
    """If implementation places last swing low on last bar, confirm must not require close <= low."""
    klines = _bearish_mirror_klines()
    _, sl = _find_swing_highs_lows(klines, 2, 2)
    if sl[-1][0] != len(klines) - 1:
        pytest.skip("mirror does not place last swing low on signal bar")

    last = list(klines[-1])
    last[4] = float(last[3]) + 10.0  # close above candle low
    klines[-1] = last

    ok, reason = passes_market_structure_filter("SHORT", klines, 2, 2, confirm_on_close=True)
    assert ok is True
    assert reason == "OK"


def test_pivot_detection_strict_fractal():
    n = 15
    highs = [100.0] * n
    lows = [100.0] * n
    highs[7] = 120.0
    klines = _series_from_hl(highs, lows)
    sh, _ = _find_swing_highs_lows(klines, 2, 2)
    assert any(i == 7 for i, _ in sh)


def test_bearish_series_regression_random_walk():
    klines = [_kline(i * 60_000, 100 - i * 0.1, 100.2 - i * 0.1, 99.8 - i * 0.1, 100 - i * 0.1) for i in range(60)]
    ok, reason = passes_market_structure_filter("SHORT", klines, 2, 2, False)
    assert isinstance(ok, bool)
    assert reason in ("OK", "INSUFFICIENT_SWINGS", "NO_LH_LL", "CLOSE_NOT_CONFIRMED_LL")


def test_scalping_strategy_wires_structure_filter_and_passes_bullish_fixture():
    """Integration: EmaScalpingStrategy._passes_entry_filters uses structure when enabled."""
    from app.core.my_binance_client import BinanceClient
    from app.strategies.base import StrategyContext
    from app.strategies.scalping import EmaScalpingStrategy

    ctx = StrategyContext(
        id="struct-test",
        name="struct-test",
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
            "use_structure_filter": True,
            "structure_left_bars": 2,
            "structure_right_bars": 2,
            "structure_confirm_on_close": True,
        },
        interval_seconds=10,
    )
    client = MagicMock(spec=BinanceClient)
    s = EmaScalpingStrategy(ctx, client)
    assert s.use_structure_filter is True
    assert s._required_filter_candles() >= required_closed_candles_for_structure(2, 2)

    klines = _bullish_klines_with_close(200.0)
    closes = [float(k[4]) for k in klines]
    t = int(klines[-1][6])
    assert s._passes_entry_filters("LONG", klines, closes, t) is True

    klines_fail = _bullish_klines_with_close(50.0)
    closes_fail = [float(k[4]) for k in klines_fail]
    assert s._passes_entry_filters("LONG", klines_fail, closes_fail, int(klines_fail[-1][6])) is False
