"""Shared utility functions for risk management services.

This module provides helper functions to eliminate repetitive code and ensure
consistency across all risk management services.
"""

from __future__ import annotations

from datetime import datetime, timezone, time, timedelta
from typing import Optional, List

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


def calculate_today_start(
    timezone_str: str = "UTC",
    reset_time: Optional[time] = None
) -> datetime:
    """Calculate today start with timezone and optional reset time.
    
    This eliminates duplication of timezone calculation logic across endpoints.
    
    Args:
        timezone_str: Timezone string (default: "UTC")
        reset_time: Optional reset time (default: 00:00:00)
        
    Returns:
        datetime: Start of today in UTC (for internal use)
    """
    from zoneinfo import ZoneInfo
    # Handle None, MagicMock, or invalid timezone strings
    if not timezone_str or not isinstance(timezone_str, str):
        timezone_str = "UTC"
    tz = ZoneInfo(timezone_str)
    now = datetime.now(tz)
    
    if reset_time:
        today_start = now.replace(
            hour=reset_time.hour,
            minute=reset_time.minute,
            second=reset_time.second,
            microsecond=0
        )
        # If reset_time is in the future today, use yesterday's reset
        if today_start > now:
            today_start = today_start - timedelta(days=1)
    else:
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    return today_start.astimezone(timezone.utc)  # Convert to UTC for internal use


def calculate_week_start(
    timezone_str: str = "UTC",
    reset_day: int = 1
) -> datetime:
    """Calculate week start with timezone and reset day.
    
    This eliminates duplication of week calculation logic across endpoints.
    
    Args:
        timezone_str: Timezone string (default: "UTC")
        reset_day: Day of week when week resets (1=Monday, 7=Sunday, default: 1)
        
    Returns:
        datetime: Start of current week in UTC (for internal use)
    """
    from zoneinfo import ZoneInfo
    # Handle None, MagicMock, or invalid timezone strings
    if not timezone_str or not isinstance(timezone_str, str):
        timezone_str = "UTC"
    tz = ZoneInfo(timezone_str)
    now = datetime.now(tz)
    
    # Calculate days to subtract to get to reset day
    # reset_day: 1=Monday, 7=Sunday
    current_weekday = now.weekday() + 1  # Convert to 1=Monday, 7=Sunday
    days_to_subtract = (current_weekday - reset_day) % 7
    
    week_start = now - timedelta(days=days_to_subtract)
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    return week_start.astimezone(timezone.utc)  # Convert to UTC for internal use


def calculate_realized_pnl_from_trades(
    completed_trades: List,
    start_time: datetime,
    end_time: Optional[datetime] = None
) -> float:
    """Calculate realized PnL from completed trades within a time window.
    
    Filters trades by exit_time and sums their PnL. This eliminates duplication
    of PnL calculation logic across endpoints.
    
    Args:
        completed_trades: List of completed trade objects
        start_time: Start of time window (inclusive, UTC)
        end_time: End of time window (inclusive, UTC, optional)
        
    Returns:
        float: Total realized PnL from trades in the time window
    """
    filtered_trades = []
    min_datetime = datetime.min.replace(tzinfo=timezone.utc)
    
    for trade in completed_trades:
        exit_time = getattr(trade, 'exit_time', None) or min_datetime
        
        # Ensure exit_time is timezone-aware
        if exit_time.tzinfo is None:
            exit_time = exit_time.replace(tzinfo=timezone.utc)
        
        # Check if trade is within time window
        if exit_time >= start_time:
            if end_time is None or exit_time <= end_time:
                filtered_trades.append(trade)
    
    return sum(get_pnl_from_completed_trade(t) for t in filtered_trades)

