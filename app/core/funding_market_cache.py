"""TTL-cached public Binance futures data for funding interval and REST PnL enrichment."""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional, Tuple

import requests
from loguru import logger

_INTERVAL_LOCK = threading.Lock()
_interval_maps: Dict[bool, Dict[str, int]] = {}
_interval_loaded_at: Dict[bool, float] = {}
_INTERVAL_TTL_SEC = 3600.0


def _fapi_base(testnet: bool) -> str:
    return (
        "https://testnet.binancefuture.com/fapi/v1"
        if testnet
        else "https://fapi.binance.com/fapi/v1"
    )


def get_funding_interval_hours(symbol: str, testnet: bool) -> Optional[int]:
    """Return ``fundingIntervalHours`` for symbol from ``/fapi/v1/fundingInfo`` (cached)."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    now = time.time()
    with _INTERVAL_LOCK:
        need_fetch = testnet not in _interval_loaded_at or (
            now - _interval_loaded_at[testnet] > _INTERVAL_TTL_SEC
        )
        if need_fetch:
            try:
                url = f"{_fapi_base(testnet)}/fundingInfo"
                r = requests.get(url, timeout=10.0)
                r.raise_for_status()
                rows = r.json()
                m: Dict[str, int] = {}
                for row in rows or []:
                    s = (row.get("symbol") or "").strip().upper()
                    if not s:
                        continue
                    try:
                        m[s] = int(row.get("fundingIntervalHours", 8))
                    except (TypeError, ValueError):
                        m[s] = 8
                _interval_maps[testnet] = m
                _interval_loaded_at[testnet] = now
            except Exception as exc:
                logger.debug(f"fundingInfo fetch failed (testnet={testnet}): {exc}")
                if testnet not in _interval_maps:
                    _interval_maps[testnet] = {}
                _interval_loaded_at[testnet] = now
        return _interval_maps.get(testnet, {}).get(sym)


def get_premium_index_funding(
    symbol: str, testnet: bool
) -> Tuple[Optional[float], Optional[int]]:
    """Fetch ``lastFundingRate`` and ``nextFundingTime`` for one symbol (no cache; use sparingly)."""
    from app.core.funding_from_mark import parse_funding_from_payload

    sym = (symbol or "").strip().upper()
    if not sym:
        return None, None
    try:
        url = f"{_fapi_base(testnet)}/premiumIndex"
        r = requests.get(url, params={"symbol": sym}, timeout=10.0)
        r.raise_for_status()
        data = r.json()
        return parse_funding_from_payload(data)
    except Exception as exc:
        logger.debug(f"premiumIndex {sym} (testnet={testnet}): {exc}")
        return None, None


def get_position_funding_for_rest(
    symbol: str, testnet: bool
) -> Tuple[Optional[float], Optional[int], Optional[int]]:
    """Rate, next funding ms, interval hours for REST ``PositionSummary`` (one premiumIndex + cache)."""
    rate, next_ms = get_premium_index_funding(symbol, testnet)
    interval_h = get_funding_interval_hours(symbol, testnet)
    return rate, next_ms, interval_h
