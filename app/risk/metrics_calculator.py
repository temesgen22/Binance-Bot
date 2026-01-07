"""
Risk metrics calculation and tracking.

Phase 4: Metrics & Monitoring
- Sharpe ratio calculation
- Profit factor calculation
- Max drawdown tracking
- Real-time metrics updates
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
from collections import deque

from loguru import logger
import math


@dataclass
class RiskMetrics:
    """Risk metrics for a strategy or portfolio."""
    strategy_id: Optional[str] = None
    account_id: Optional[str] = None
    
    # Performance Metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0  # Percentage (0-100)
    
    # PnL Metrics
    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0  # gross_profit / abs(gross_loss)
    avg_win: float = 0.0
    avg_loss: float = 0.0
    
    # Risk Metrics
    sharpe_ratio: Optional[float] = None
    max_drawdown_pct: float = 0.0
    max_drawdown_usdt: float = 0.0
    current_drawdown_pct: float = 0.0
    current_drawdown_usdt: float = 0.0
    
    # Balance Tracking
    peak_balance: float = 0.0
    current_balance: float = 0.0
    initial_balance: float = 0.0
    
    # Time Tracking
    calculated_at: datetime = None
    
    def __post_init__(self):
        """Set default calculated_at if not provided."""
        if self.calculated_at is None:
            self.calculated_at = datetime.now(timezone.utc)


class RiskMetricsCalculator:
    """Calculates risk metrics for strategies and portfolios.
    
    Features:
    - Sharpe ratio calculation
    - Profit factor calculation
    - Max drawdown tracking
    - Real-time metrics updates
    """
    
    def __init__(
        self,
        risk_free_rate: float = 0.0,  # Risk-free rate (default 0% for crypto)
        lookback_days: int = 90,  # Lookback period for Sharpe ratio
    ):
        """Initialize risk metrics calculator.
        
        Args:
            risk_free_rate: Risk-free rate for Sharpe ratio (default 0% for crypto)
            lookback_days: Lookback period for Sharpe ratio calculation
        """
        self.risk_free_rate = risk_free_rate
        self.lookback_days = lookback_days
    
    def calculate_metrics(
        self,
        trades: List[Dict],  # List of trade dicts with 'pnl', 'timestamp', etc.
        initial_balance: float,
        current_balance: float,
        peak_balance: Optional[float] = None,
    ) -> RiskMetrics:
        """Calculate comprehensive risk metrics from trades.
        
        Args:
            trades: List of trade dictionaries with at least 'pnl' field
            initial_balance: Initial account balance
            current_balance: Current account balance
            peak_balance: Peak balance (if None, calculated from trades)
            
        Returns:
            RiskMetrics object
        """
        if not trades:
            return RiskMetrics(
                initial_balance=initial_balance,
                current_balance=current_balance,
                peak_balance=current_balance,
            )
        
        # Filter to lookback period for Sharpe ratio
        lookback_start = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        recent_trades = [
            t for t in trades
            if isinstance(t.get('timestamp'), datetime) and t['timestamp'] >= lookback_start
        ]
        
        # Basic trade statistics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in trades if t.get('pnl', 0) < 0]
        
        winning_count = len(winning_trades)
        losing_count = len(losing_trades)
        win_rate = (winning_count / total_trades * 100) if total_trades > 0 else 0.0
        
        # PnL statistics
        total_pnl = sum(t.get('pnl', 0) for t in trades)
        gross_profit = sum(t.get('pnl', 0) for t in winning_trades)
        gross_loss = abs(sum(t.get('pnl', 0) for t in losing_trades))
        
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)
        
        avg_win = gross_profit / winning_count if winning_count > 0 else 0.0
        avg_loss = gross_loss / losing_count if losing_count > 0 else 0.0
        
        # Calculate Sharpe ratio
        sharpe_ratio = self._calculate_sharpe_ratio(recent_trades, initial_balance)
        
        # Calculate drawdown
        if peak_balance is None:
            peak_balance = self._calculate_peak_balance(trades, initial_balance)
        
        max_drawdown_pct, max_drawdown_usdt = self._calculate_max_drawdown(
            trades, initial_balance, peak_balance
        )
        
        current_drawdown_pct = ((peak_balance - current_balance) / peak_balance * 100) if peak_balance > 0 else 0.0
        current_drawdown_usdt = peak_balance - current_balance
        
        return RiskMetrics(
            total_trades=total_trades,
            winning_trades=winning_count,
            losing_trades=losing_count,
            win_rate=win_rate,
            total_pnl=total_pnl,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            sharpe_ratio=sharpe_ratio,
            max_drawdown_pct=max_drawdown_pct,
            max_drawdown_usdt=max_drawdown_usdt,
            current_drawdown_pct=current_drawdown_pct,
            current_drawdown_usdt=current_drawdown_usdt,
            peak_balance=peak_balance,
            current_balance=current_balance,
            initial_balance=initial_balance,
        )
    
    def _calculate_sharpe_ratio(
        self,
        trades: List[Dict],
        initial_balance: float
    ) -> Optional[float]:
        """Calculate Sharpe ratio.
        
        Sharpe Ratio = (Average Return - Risk-Free Rate) / Standard Deviation of Returns
        
        Args:
            trades: List of trades with 'pnl' and 'timestamp'
            initial_balance: Initial balance for return calculation
            
        Returns:
            Sharpe ratio or None if insufficient data
        """
        if len(trades) < 2 or initial_balance <= 0:
            return None
        
        # Calculate returns (percentage of balance)
        returns = []
        running_balance = initial_balance
        
        for trade in sorted(trades, key=lambda t: t.get('timestamp', datetime.now(timezone.utc))):
            pnl = trade.get('pnl', 0)
            if running_balance > 0:
                return_pct = (pnl / running_balance) * 100
                returns.append(return_pct)
                running_balance += pnl
        
        if len(returns) < 2:
            return None
        
        # Calculate average return
        avg_return = sum(returns) / len(returns)
        
        # Calculate standard deviation
        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
        std_dev = math.sqrt(variance)
        
        if std_dev == 0:
            return None  # No volatility
        
        # Calculate Sharpe ratio (annualized)
        # Assuming daily returns, annualize by multiplying by sqrt(252)
        sharpe = (avg_return - self.risk_free_rate) / std_dev * math.sqrt(252)
        
        return sharpe
    
    def _calculate_peak_balance(
        self,
        trades: List[Dict],
        initial_balance: float
    ) -> float:
        """Calculate peak balance from trades.
        
        Args:
            trades: List of trades with 'pnl' and 'timestamp'
            initial_balance: Initial balance
            
        Returns:
            Peak balance
        """
        peak = initial_balance
        current = initial_balance
        
        for trade in sorted(trades, key=lambda t: t.get('timestamp', datetime.now(timezone.utc))):
            current += trade.get('pnl', 0)
            if current > peak:
                peak = current
        
        return peak
    
    def _calculate_max_drawdown(
        self,
        trades: List[Dict],
        initial_balance: float,
        peak_balance: float
    ) -> tuple[float, float]:
        """Calculate maximum drawdown.
        
        Args:
            trades: List of trades with 'pnl' and 'timestamp'
            initial_balance: Initial balance
            peak_balance: Peak balance
            
        Returns:
            (max_drawdown_pct, max_drawdown_usdt) tuple
        """
        if peak_balance <= 0:
            return 0.0, 0.0
        
        max_drawdown_usdt = 0.0
        peak = initial_balance
        current = initial_balance
        
        for trade in sorted(trades, key=lambda t: t.get('timestamp', datetime.now(timezone.utc))):
            current += trade.get('pnl', 0)
            if current > peak:
                peak = current
            
            drawdown = peak - current
            if drawdown > max_drawdown_usdt:
                max_drawdown_usdt = drawdown
        
        max_drawdown_pct = (max_drawdown_usdt / peak_balance * 100) if peak_balance > 0 else 0.0
        
        return max_drawdown_pct, max_drawdown_usdt
    
    def update_metrics(
        self,
        existing_metrics: RiskMetrics,
        new_trades: List[Dict],
        current_balance: float,
    ) -> RiskMetrics:
        """Update existing metrics with new trades.
        
        Args:
            existing_metrics: Existing RiskMetrics object
            new_trades: New trades to add
            current_balance: Current balance
            
        Returns:
            Updated RiskMetrics
        """
        # Combine existing trades with new trades
        # In production, this would fetch from database
        all_trades = new_trades  # Simplified - would merge with existing
        
        return self.calculate_metrics(
            trades=all_trades,
            initial_balance=existing_metrics.initial_balance,
            current_balance=current_balance,
            peak_balance=max(existing_metrics.peak_balance, current_balance)
        )














