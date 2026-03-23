"""
Market structure (HH/HL vs LH/LL) entry filter for EMA scalping strategies.

Uses closed-candle highs/lows for swing pivots; optional close-based confirmation.
LONG: Higher High + Higher Low (last two swing highs and lows vs prior pair).
SHORT: Lower High + Lower Low.
"""

from __future__ import annotations

import math
from typing import List, Literal, Tuple


def _parse_high_low(kline: list) -> Tuple[float, float]:
    return float(kline[2]), float(kline[3])


def _find_swing_highs_lows(
    closed_klines: List[list],
    left: int,
    right: int,
) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """
    Return (swing_highs, swing_lows) as lists of (bar_index, price).
    Pivots use strict comparison vs left/right windows (closed candles only).
    """
    n = len(closed_klines)
    if n < left + right + 1 or left < 1 or right < 1:
        return [], []

    highs: List[float] = []
    lows: List[float] = []
    for k in closed_klines:
        h, l_ = _parse_high_low(k)
        highs.append(h)
        lows.append(l_)

    swing_highs: List[Tuple[int, float]] = []
    swing_lows: List[Tuple[int, float]] = []

    for i in range(left, n - right):
        hi = highs[i]
        left_max = max(highs[i - left : i])
        right_max = max(highs[i + 1 : i + right + 1])
        if hi > left_max and hi > right_max:
            swing_highs.append((i, hi))

        lo = lows[i]
        left_min = min(lows[i - left : i])
        right_min = min(lows[i + 1 : i + right + 1])
        if lo < left_min and lo < right_min:
            swing_lows.append((i, lo))

    return swing_highs, swing_lows


def required_closed_candles_for_structure(left: int, right: int) -> int:
    """Minimum closed candles needed before evaluating structure (fail-closed if fewer)."""
    lr = max(1, left, right)
    # Room for multiple pivots; conservative lower bound
    return max(20, (lr + lr + 1) * 4)


def passes_market_structure_filter(
    candidate_side: Literal["LONG", "SHORT"],
    closed_klines: List[list],
    left: int,
    right: int,
    confirm_on_close: bool,
) -> Tuple[bool, str]:
    """
    Returns (pass, reason_code).

    LONG: last two swing highs show HH; last two swing lows show HL.
    SHORT: last two swing highs show LH; last two swing lows show LL.

    If confirm_on_close:
      LONG: close must be at/above the *previous* swing high (h_prev) — breakout of prior resistance
            (avoids impossible close >= wick when the newest swing high is on the signal bar).
      SHORT: if the last swing low is not on the signal bar, close <= that swing low; if the pivot
             is on the last bar, skip this check (close is almost never <= candle low).
    """
    if not closed_klines:
        return False, "INSUFFICIENT_DATA"

    last_close = float(closed_klines[-1][4])
    if not math.isfinite(last_close):
        return False, "INVALID_CLOSE"

    swing_highs, swing_lows = _find_swing_highs_lows(closed_klines, left, right)
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return False, "INSUFFICIENT_SWINGS"

    (_, h_prev), (_, h_last) = swing_highs[-2], swing_highs[-1]
    (_, l_prev), (_, l_last) = swing_lows[-2], swing_lows[-1]

    if candidate_side == "LONG":
        if not (h_last > h_prev and l_last > l_prev):
            return False, "NO_HH_HL"
        # Confirm close broke above prior swing high (not the latest pivot high, which is often the bar wick).
        if confirm_on_close and last_close < h_prev:
            return False, "CLOSE_NOT_CONFIRMED_HH"
        return True, "OK"

    # SHORT
    if not (h_last < h_prev and l_last < l_prev):
        return False, "NO_LH_LL"
    if confirm_on_close:
        idx_l_last = swing_lows[-1][0]
        last_i = len(closed_klines) - 1
        # If the most recent swing low is on the signal bar, close <= l_last would require close at the low (rare).
        if idx_l_last != last_i and last_close > l_last:
            return False, "CLOSE_NOT_CONFIRMED_LL"
    return True, "OK"
