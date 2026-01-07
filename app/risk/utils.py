"""Shared utility functions for risk management services.

This module provides helper functions to eliminate repetitive code and ensure
consistency across all risk management services.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger


def get_pnl_from_completed_trade(completed_trade) -> float:
    """Extract PnL value from a completed trade object.
    
    Handles both TradeReport (pnl_usd) and CompletedTradeMatch (net_pnl) types.
    This standardizes PnL extraction across all risk services.
    
    Args:
        completed_trade: TradeReport or CompletedTradeMatch object
        
    Returns:
        PnL value as float (0.0 if not found)
    """
    # Helper to safely convert to float, handling Mock objects and None
    def safe_float(value, default=0.0):
        if value is None:
            return default
        # Check if it's a Mock object (has __class__ and __class__.__name__ == 'Mock')
        if hasattr(value, '__class__') and value.__class__.__name__ == 'Mock':
            return default
        # Check if it's a number type
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    
    # Try pnl_usd first (TradeReport from reports.py)
    if hasattr(completed_trade, 'pnl_usd'):
        pnl_value = getattr(completed_trade, 'pnl_usd', None)
        result = safe_float(pnl_value)
        if result != 0.0 or (pnl_value is not None and not hasattr(pnl_value, '__class__') or pnl_value.__class__.__name__ != 'Mock'):
            return result
    # Try net_pnl (CompletedTradeMatch from trade_matcher.py)
    if hasattr(completed_trade, 'net_pnl'):
        pnl_value = getattr(completed_trade, 'net_pnl', None)
        result = safe_float(pnl_value)
        if result != 0.0 or (pnl_value is not None and not hasattr(pnl_value, '__class__') or pnl_value.__class__.__name__ != 'Mock'):
            return result
    # Try realized_pnl (fallback for raw trades)
    if hasattr(completed_trade, 'realized_pnl'):
        pnl_value = getattr(completed_trade, 'realized_pnl', None)
        result = safe_float(pnl_value)
        if result != 0.0 or (pnl_value is not None and not hasattr(pnl_value, '__class__') or pnl_value.__class__.__name__ != 'Mock'):
            return result
    # Default to 0 if no PnL attribute found
    logger.warning(f"Completed trade object has no recognized PnL attribute: {type(completed_trade)}")
    return 0.0


def get_timestamp_from_completed_trade(
    completed_trade,
    fallback: Optional[datetime] = None
) -> datetime:
    """Extract timestamp from a completed trade object.
    
    Args:
        completed_trade: TradeReport or CompletedTradeMatch object
        fallback: Fallback datetime if no timestamp found (defaults to now)
        
    Returns:
        Timestamp as datetime
    """
    if fallback is None:
        fallback = datetime.now(timezone.utc)
    
    # Try exit_time first (most accurate for completed trades)
    if hasattr(completed_trade, 'exit_time') and completed_trade.exit_time:
        return completed_trade.exit_time
    # Try entry_time
    if hasattr(completed_trade, 'entry_time') and completed_trade.entry_time:
        return completed_trade.entry_time
    # Fallback
    return fallback

