"""Parse funding fields from Binance mark-price payloads (WebSocket or REST premiumIndex)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def parse_funding_from_payload(data: Dict[str, Any]) -> Tuple[Optional[float], Optional[int]]:
    """Extract last funding rate and next funding time (ms) from a unified payload.

    WebSocket ``markPriceUpdate`` uses ``r`` and ``T``; REST ``premiumIndex`` uses
    ``lastFundingRate`` and ``nextFundingTime``.
    """
    if not data:
        return None, None
    rate: Optional[float] = None
    raw_rate = data.get("r")
    if raw_rate is None:
        raw_rate = data.get("lastFundingRate")
    if raw_rate is not None:
        try:
            rate = float(raw_rate)
        except (TypeError, ValueError):
            rate = None

    t_ms: Optional[int] = None
    raw_t = data.get("T")
    if raw_t is None:
        raw_t = data.get("nextFundingTime")
    if raw_t is not None:
        try:
            t_ms = int(float(raw_t))
        except (TypeError, ValueError):
            t_ms = None

    return rate, t_ms
