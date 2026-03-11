"""
Market regime analyzer for circuit breaker: suggest why strategy may be underperforming.

When the circuit breaker triggers (e.g. N consecutive losses), this module analyzes
recent price action and returns a short, human-readable reason, e.g.:
  "Market is ranging; strategy is trend-following (EMA crossover)."

Caller provides klines (no Binance dependency here). Use from strategy_executor or
order_manager after fetching klines via strategy.get_klines() or kline manager.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from loguru import logger


@dataclass
class MarketRegimeResult:
    """Result of market regime analysis for circuit breaker."""
    regime: str          # "trending", "ranging", "unknown"
    volatility: str       # "high", "normal", "low"
    reason: str          # Short sentence for notifications/UI
    meta: dict           # Optional: adx_ratio, atr_pct, net_move_pct, etc.


def _parse_klines(klines: List[Any]) -> List[tuple]:
    """Convert Binance-style klines to (open, high, low, close) tuples. Handles list or tuple rows."""
    out = []
    for k in (klines or []):
        if isinstance(k, (list, tuple)) and len(k) >= 5:
            try:
                o, h, l, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
                out.append((o, h, l, c))
            except (TypeError, ValueError):
                continue
    return out


def _atr_pct(ohlc: List[tuple], period: int = 14) -> float:
    """Average True Range as % of current price (approximate)."""
    if not ohlc or len(ohlc) < 2 or period < 1:
        return 0.0
    trs = []
    for i in range(1, min(len(ohlc), period + 1)):
        prev_c = ohlc[i - 1][3]
        h, l, c = ohlc[i][1], ohlc[i][2], ohlc[i][3]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    if not trs:
        return 0.0
    avg_tr = sum(trs) / len(trs)
    current_price = ohlc[-1][3]
    if current_price <= 0:
        return 0.0
    return (avg_tr / current_price) * 100.0


def analyze_market_regime(
    klines: List[Any],
    strategy_type: Optional[str] = None,
    symbol: str = "",
) -> MarketRegimeResult:
    """
    Analyze recent price action and return regime + suggested reason for circuit breaker.

    Args:
        klines: List of Binance-style klines [open_time, open, high, low, close, volume, ...]
        strategy_type: e.g. "ema_crossover", "range_mean_reversion", "scalping", "reverse_scalping"
        symbol: Optional symbol for the reason string (e.g. "BTCUSDT")

    Returns:
        MarketRegimeResult with regime, volatility, and a short reason string.
    """
    ohlc = _parse_klines(klines)
    if len(ohlc) < 10:
        return MarketRegimeResult(
            regime="unknown",
            volatility="normal",
            reason="Not enough price data to analyze market regime.",
            meta={"candles": len(ohlc)},
        )

    # Use last 50 candles (or all) for regime
    lookback = min(50, len(ohlc))
    recent = ohlc[-lookback:]
    first_close = recent[0][3]
    last_close = recent[-1][3]
    current_price = last_close or first_close or 1.0

    # Net move over period (as %)
    net_move_pct = 0.0
    if first_close and first_close > 0:
        net_move_pct = ((last_close - first_close) / first_close) * 100.0

    # ATR as % of price (volatility)
    atr_pct = _atr_pct(recent, period=min(14, lookback))

    # Total range (sum of high-low) vs net move (abs) to detect ranging
    total_range = sum(h - l for _, h, l, _ in recent)
    avg_range_pct = (total_range / len(recent) / current_price) * 100.0 if current_price else 0
    abs_net_move = abs(net_move_pct)

    # Simple regime: if net move is small relative to typical range → ranging
    # Threshold: net move < ~0.5 * average range % → ranging
    if avg_range_pct > 0 and abs_net_move < 0.5 * avg_range_pct:
        regime = "ranging"
    elif abs_net_move > avg_range_pct * 1.5:
        regime = "trending"
    else:
        regime = "unknown"

    # Volatility bands (example: ATR %)
    if atr_pct > 0.5:
        volatility = "high"
    elif atr_pct < 0.1:
        volatility = "low"
    else:
        volatility = "normal"

    # Build reason string from strategy type + regime
    strategy_label = (strategy_type or "strategy").replace("_", " ").title()
    if regime == "ranging":
        if strategy_type in ("ema_crossover", "scalping", "reverse_scalping"):
            reason = (
                f"Market appears ranging (low directional move). "
                f"{strategy_label} typically performs better in trending markets."
            )
        elif strategy_type == "range_mean_reversion":
            reason = (
                f"Market is ranging. {strategy_label} is designed for range conditions; "
                f"consecutive losses may be due to range boundaries or volatility."
            )
        else:
            reason = f"Market appears ranging. Consider whether {strategy_label} suits current conditions."
    elif regime == "trending":
        if strategy_type == "range_mean_reversion":
            reason = (
                f"Market is trending. {strategy_label} is designed for ranging markets; "
                f"trending conditions can cause repeated stop-outs."
            )
        else:
            reason = (
                f"Market is trending. If losses persist, check entry/exit logic or risk parameters."
            )
    else:
        reason = (
            f"Market regime unclear. {strategy_label} had consecutive losses; "
            f"consider reviewing parameters or pausing until conditions improve."
        )

    if symbol:
        reason = f"[{symbol}] " + reason

    meta = {
        "regime": regime,
        "volatility": volatility,
        "net_move_pct": round(net_move_pct, 4),
        "atr_pct": round(atr_pct, 4),
        "candles": lookback,
    }
    return MarketRegimeResult(regime=regime, volatility=volatility, reason=reason.strip(), meta=meta)
