"""Open PnL giveback stop: close when unrealized PnL falls by X USDT from peak since entry."""

from __future__ import annotations

from typing import Optional, Tuple


def update_peak_unrealized(
    prior_peak: Optional[float],
    current_unrealized: float,
) -> float:
    """Running maximum of unrealized PnL for the open position."""
    if prior_peak is None:
        return current_unrealized
    return max(prior_peak, current_unrealized)


def giveback_should_trigger(
    *,
    peak_unrealized: float,
    current_unrealized: float,
    min_peak_usdt: float,
    giveback_usdt: float,
) -> Tuple[bool, str]:
    """
    Returns (should_close, reason_snippet).

    Requires peak unrealized to have reached at least min_peak_usdt before the rule is armed.
    Triggers when (peak - current) >= giveback_usdt.
    """
    if giveback_usdt <= 0:
        return False, "giveback_usdt<=0"
    if peak_unrealized < min_peak_usdt:
        return False, "below_min_peak"
    drawdown = peak_unrealized - current_unrealized
    if drawdown >= giveback_usdt:
        return True, f"drawdown={drawdown:.4f}>={giveback_usdt:.4f}"
    return False, "under_threshold"
