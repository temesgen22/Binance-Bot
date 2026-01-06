"""
Trade frequency limiting to prevent overtrading.

Phase 3 Week 6: Trade Frequency Limits
- Per-strategy trade frequency limits
- Per-account trade frequency limits
- Time-windowed tracking
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque

from loguru import logger

from app.core.exceptions import RiskLimitExceededError


@dataclass
class TradeFrequencyLimit:
    """Trade frequency limit configuration."""
    max_trades_per_minute: Optional[int] = None
    max_trades_per_hour: Optional[int] = None
    max_trades_per_day: Optional[int] = None
    max_trades_per_week: Optional[int] = None


@dataclass
class TradeFrequencyStatus:
    """Current trade frequency status."""
    account_id: str
    strategy_id: Optional[str]
    trades_last_minute: int
    trades_last_hour: int
    trades_last_day: int
    trades_last_week: int
    limit_breached: bool
    breach_reason: Optional[str] = None


class TradeFrequencyLimiter:
    """Limits trade frequency to prevent overtrading.
    
    Features:
    - Per-strategy limits
    - Per-account limits
    - Multiple time windows (minute, hour, day, week)
    - Automatic blocking when limits exceeded
    """
    
    def __init__(
        self,
        account_limits: Optional[TradeFrequencyLimit] = None,
        strategy_limits: Optional[TradeFrequencyLimit] = None,
    ):
        """Initialize trade frequency limiter.
        
        Args:
            account_limits: Account-level limits (optional)
            strategy_limits: Strategy-level limits (optional)
        """
        self.account_limits = account_limits or TradeFrequencyLimit()
        self.strategy_limits = strategy_limits or TradeFrequencyLimit()
        
        # Track trades: {account_id: {strategy_id: deque of timestamps}}
        self._trade_timestamps: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
        
        # Cleanup old entries periodically
        self._last_cleanup = datetime.now(timezone.utc)
        self._cleanup_interval = timedelta(hours=1)
    
    def record_trade(
        self,
        account_id: str,
        strategy_id: str,
        timestamp: Optional[datetime] = None
    ) -> None:
        """Record a trade for frequency tracking.
        
        Args:
            account_id: Account ID
            strategy_id: Strategy ID
            timestamp: Trade timestamp (default: now)
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        # Add to tracking
        self._trade_timestamps[account_id][strategy_id].append(timestamp)
        
        # Periodic cleanup
        if datetime.now(timezone.utc) - self._last_cleanup > self._cleanup_interval:
            self._cleanup_old_entries()
            self._last_cleanup = datetime.now(timezone.utc)
    
    def check_trade_allowed(
        self,
        account_id: str,
        strategy_id: str,
        timestamp: Optional[datetime] = None
    ) -> Tuple[bool, Optional[str]]:
        """Check if a trade is allowed based on frequency limits.
        
        Args:
            account_id: Account ID
            strategy_id: Strategy ID
            timestamp: Check timestamp (default: now)
            
        Returns:
            (allowed, reason) tuple
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        # Cleanup old entries first
        self._cleanup_old_entries()
        
        # Get current trade counts
        account_trades = self._get_account_trades(account_id, timestamp)
        strategy_trades = self._get_strategy_trades(account_id, strategy_id, timestamp)
        
        # Check account-level limits
        if self.account_limits.max_trades_per_minute:
            trades_last_minute = self._count_trades_in_window(
                account_trades, timestamp, timedelta(minutes=1)
            )
            if trades_last_minute >= self.account_limits.max_trades_per_minute:
                return False, (
                    f"Account trade frequency limit exceeded: "
                    f"{trades_last_minute} trades in last minute "
                    f"(limit: {self.account_limits.max_trades_per_minute})"
                )
        
        if self.account_limits.max_trades_per_hour:
            trades_last_hour = self._count_trades_in_window(
                account_trades, timestamp, timedelta(hours=1)
            )
            if trades_last_hour >= self.account_limits.max_trades_per_hour:
                return False, (
                    f"Account trade frequency limit exceeded: "
                    f"{trades_last_hour} trades in last hour "
                    f"(limit: {self.account_limits.max_trades_per_hour})"
                )
        
        if self.account_limits.max_trades_per_day:
            trades_last_day = self._count_trades_in_window(
                account_trades, timestamp, timedelta(days=1)
            )
            if trades_last_day >= self.account_limits.max_trades_per_day:
                return False, (
                    f"Account trade frequency limit exceeded: "
                    f"{trades_last_day} trades in last day "
                    f"(limit: {self.account_limits.max_trades_per_day})"
                )
        
        if self.account_limits.max_trades_per_week:
            trades_last_week = self._count_trades_in_window(
                account_trades, timestamp, timedelta(weeks=1)
            )
            if trades_last_week >= self.account_limits.max_trades_per_week:
                return False, (
                    f"Account trade frequency limit exceeded: "
                    f"{trades_last_week} trades in last week "
                    f"(limit: {self.account_limits.max_trades_per_week})"
                )
        
        # Check strategy-level limits
        if self.strategy_limits.max_trades_per_minute:
            trades_last_minute = self._count_trades_in_window(
                strategy_trades, timestamp, timedelta(minutes=1)
            )
            if trades_last_minute >= self.strategy_limits.max_trades_per_minute:
                return False, (
                    f"Strategy trade frequency limit exceeded: "
                    f"{trades_last_minute} trades in last minute "
                    f"(limit: {self.strategy_limits.max_trades_per_minute})"
                )
        
        if self.strategy_limits.max_trades_per_hour:
            trades_last_hour = self._count_trades_in_window(
                strategy_trades, timestamp, timedelta(hours=1)
            )
            if trades_last_hour >= self.strategy_limits.max_trades_per_hour:
                return False, (
                    f"Strategy trade frequency limit exceeded: "
                    f"{trades_last_hour} trades in last hour "
                    f"(limit: {self.strategy_limits.max_trades_per_hour})"
                )
        
        if self.strategy_limits.max_trades_per_day:
            trades_last_day = self._count_trades_in_window(
                strategy_trades, timestamp, timedelta(days=1)
            )
            if trades_last_day >= self.strategy_limits.max_trades_per_day:
                return False, (
                    f"Strategy trade frequency limit exceeded: "
                    f"{trades_last_day} trades in last day "
                    f"(limit: {self.strategy_limits.max_trades_per_day})"
                )
        
        if self.strategy_limits.max_trades_per_week:
            trades_last_week = self._count_trades_in_window(
                strategy_trades, timestamp, timedelta(weeks=1)
            )
            if trades_last_week >= self.strategy_limits.max_trades_per_week:
                return False, (
                    f"Strategy trade frequency limit exceeded: "
                    f"{trades_last_week} trades in last week "
                    f"(limit: {self.strategy_limits.max_trades_per_week})"
                )
        
        return True, None
    
    def get_frequency_status(
        self,
        account_id: str,
        strategy_id: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> TradeFrequencyStatus:
        """Get current trade frequency status.
        
        Args:
            account_id: Account ID
            strategy_id: Strategy ID (optional)
            timestamp: Check timestamp (default: now)
            
        Returns:
            TradeFrequencyStatus
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        # Get trade counts
        account_trades = self._get_account_trades(account_id, timestamp)
        
        trades_last_minute = self._count_trades_in_window(
            account_trades, timestamp, timedelta(minutes=1)
        )
        trades_last_hour = self._count_trades_in_window(
            account_trades, timestamp, timedelta(hours=1)
        )
        trades_last_day = self._count_trades_in_window(
            account_trades, timestamp, timedelta(days=1)
        )
        trades_last_week = self._count_trades_in_window(
            account_trades, timestamp, timedelta(weeks=1)
        )
        
        # Check if limits are breached
        allowed, reason = self.check_trade_allowed(account_id, strategy_id or "", timestamp)
        
        return TradeFrequencyStatus(
            account_id=account_id,
            strategy_id=strategy_id,
            trades_last_minute=trades_last_minute,
            trades_last_hour=trades_last_hour,
            trades_last_day=trades_last_day,
            trades_last_week=trades_last_week,
            limit_breached=not allowed,
            breach_reason=reason
        )
    
    def _get_account_trades(self, account_id: str, timestamp: datetime) -> List[datetime]:
        """Get all trades for an account."""
        all_trades = []
        for strategy_trades in self._trade_timestamps[account_id].values():
            all_trades.extend(strategy_trades)
        return sorted(all_trades)
    
    def _get_strategy_trades(
        self,
        account_id: str,
        strategy_id: str,
        timestamp: datetime
    ) -> List[datetime]:
        """Get all trades for a strategy."""
        return list(self._trade_timestamps[account_id][strategy_id])
    
    def _count_trades_in_window(
        self,
        trades: List[datetime],
        timestamp: datetime,
        window: timedelta
    ) -> int:
        """Count trades within a time window."""
        window_start = timestamp - window
        return sum(1 for trade_ts in trades if trade_ts >= window_start)
    
    def _cleanup_old_entries(self) -> None:
        """Remove old trade timestamps (older than 2 weeks)."""
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=2)
        
        for account_id in list(self._trade_timestamps.keys()):
            for strategy_id in list(self._trade_timestamps[account_id].keys()):
                # Remove old timestamps
                while (self._trade_timestamps[account_id][strategy_id] and
                       self._trade_timestamps[account_id][strategy_id][0] < cutoff):
                    self._trade_timestamps[account_id][strategy_id].popleft()
                
                # Remove empty entries
                if not self._trade_timestamps[account_id][strategy_id]:
                    del self._trade_timestamps[account_id][strategy_id]
            
            # Remove empty accounts
            if not self._trade_timestamps[account_id]:
                del self._trade_timestamps[account_id]

