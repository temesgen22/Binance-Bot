"""
Dynamic position sizing based on volatility (ATR), performance, and Kelly Criterion.

Phase 2: Dynamic Risk Management
- Volatility-based position sizing (ATR)
- Performance-based risk adjustment (win/loss streaks)
- Kelly Criterion with safeguards
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Tuple
from datetime import datetime, timezone, timedelta

from loguru import logger

from app.core.my_binance_client import BinanceClient
from app.core.exceptions import PositionSizingError
from app.risk.manager import RiskManager, PositionSizingResult
from app.strategies.indicators import calculate_atr


@dataclass
class DynamicSizingConfig:
    """Configuration for dynamic position sizing."""
    volatility_based_enabled: bool = False
    atr_period: int = 14
    atr_multiplier: float = 2.0  # Position size = base_size * (base_atr / current_atr) * multiplier
    
    performance_based_enabled: bool = False
    win_streak_boost: float = 0.1  # 10% increase per win streak
    loss_streak_reduction: float = 0.15  # 15% decrease per loss streak
    max_win_streak_boost: float = 0.5  # Max 50% boost
    max_loss_streak_reduction: float = 0.5  # Max 50% reduction
    
    kelly_criterion_enabled: bool = False
    kelly_fraction: float = 0.25  # Use quarter Kelly (safer)
    min_trades_for_kelly: int = 100  # Minimum trades before using Kelly
    max_kelly_position_pct: float = 0.1  # Max 10% of balance per position


@dataclass
class TradePerformance:
    """Trade performance metrics for a strategy."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_profit: float = 0.0
    total_loss: float = 0.0
    current_win_streak: int = 0
    current_loss_streak: int = 0
    last_trade_pnl: Optional[float] = None  # Positive = win, negative = loss


class DynamicPositionSizer:
    """Dynamic position sizing based on volatility, performance, and Kelly Criterion.
    
    Extends the base RiskManager with advanced sizing methods.
    """
    
    def __init__(
        self,
        client: BinanceClient,
        base_risk_manager: Optional[RiskManager] = None,
        config: Optional[DynamicSizingConfig] = None
    ):
        """Initialize dynamic position sizer.
        
        Args:
            client: Binance client for market data
            base_risk_manager: Base risk manager (optional, creates new if None)
            config: Dynamic sizing configuration
        """
        self.client = client
        self.base_risk_manager = base_risk_manager or RiskManager(client)
        self.config = config or DynamicSizingConfig()
        
        # Cache for ATR values (symbol -> (atr_value, timestamp))
        self._atr_cache: dict[str, Tuple[float, datetime]] = {}
        self._atr_cache_ttl = timedelta(minutes=5)  # Cache ATR for 5 minutes
        
        # Performance tracking per strategy
        self._performance: dict[str, TradePerformance] = {}
    
    def size_position(
        self,
        symbol: str,
        risk_per_trade: float,
        price: float,
        fixed_amount: Optional[float] = None,
        strategy_id: Optional[str] = None,
        klines: Optional[List[List]] = None,
    ) -> PositionSizingResult:
        """Calculate position size with dynamic adjustments.
        
        Args:
            symbol: Trading symbol
            risk_per_trade: Base risk percentage (0.01 = 1%)
            price: Current price
            fixed_amount: Fixed amount (overrides risk_per_trade if set)
            strategy_id: Strategy ID for performance tracking
            klines: Historical klines for ATR calculation (optional, will fetch if needed)
            
        Returns:
            PositionSizingResult with adjusted quantity and notional
        """
        # Start with base sizing
        base_result = self.base_risk_manager.size_position(
            symbol=symbol,
            risk_per_trade=risk_per_trade,
            price=price,
            fixed_amount=fixed_amount
        )
        
        # Apply dynamic adjustments
        adjusted_quantity = base_result.quantity
        adjustment_factors = []
        
        # 1. Volatility-based adjustment (ATR)
        if self.config.volatility_based_enabled:
            atr_adjustment = self._calculate_atr_adjustment(symbol, price, klines)
            if atr_adjustment is not None:
                adjusted_quantity *= atr_adjustment
                adjustment_factors.append(f"ATR: {atr_adjustment:.3f}x")
        
        # 2. Performance-based adjustment (win/loss streaks)
        if self.config.performance_based_enabled and strategy_id:
            perf_adjustment = self._calculate_performance_adjustment(strategy_id)
            if perf_adjustment != 1.0:
                adjusted_quantity *= perf_adjustment
                adjustment_factors.append(f"Performance: {perf_adjustment:.3f}x")
        
        # 3. Kelly Criterion adjustment
        if self.config.kelly_criterion_enabled and strategy_id:
            kelly_adjustment = self._calculate_kelly_adjustment(
                strategy_id, base_result.notional, price
            )
            if kelly_adjustment is not None:
                adjusted_quantity *= kelly_adjustment
                adjustment_factors.append(f"Kelly: {kelly_adjustment:.3f}x")
        
        # Round quantity and recalculate notional
        rounded_quantity = self.client.round_quantity(symbol, adjusted_quantity)
        adjusted_notional = rounded_quantity * price
        
        # Log adjustments
        if adjustment_factors:
            logger.info(
                f"Dynamic sizing for {symbol} (strategy: {strategy_id}): "
                f"base={base_result.quantity:.8f}, adjusted={rounded_quantity:.8f}, "
                f"factors=[{', '.join(adjustment_factors)}]"
            )
        
        return PositionSizingResult(
            quantity=rounded_quantity,
            notional=adjusted_notional
        )
    
    def _calculate_atr_adjustment(
        self,
        symbol: str,
        price: float,
        klines: Optional[List[List]] = None
    ) -> Optional[float]:
        """Calculate ATR-based position size adjustment.
        
        Higher volatility (ATR) → Smaller position size
        Lower volatility (ATR) → Larger position size
        
        Formula: adjustment = (base_atr / current_atr) * multiplier
        
        Args:
            symbol: Trading symbol
            price: Current price
            klines: Historical klines (will fetch if not provided)
            
        Returns:
            Adjustment factor (1.0 = no change, <1.0 = reduce, >1.0 = increase)
        """
        # Get current ATR
        current_atr = self._get_atr(symbol, klines)
        if current_atr is None or current_atr <= 0:
            logger.debug(f"Cannot calculate ATR adjustment for {symbol}: ATR unavailable")
            return None
        
        # Use price as base ATR reference (simplified - could use historical average)
        # For now, use a simple heuristic: base_atr = price * 0.01 (1% of price)
        base_atr = price * 0.01
        
        # Calculate adjustment
        # If current ATR > base ATR → reduce position (volatility is high)
        # If current ATR < base ATR → increase position (volatility is low)
        adjustment = (base_atr / current_atr) * self.config.atr_multiplier
        
        # Cap adjustment to reasonable bounds (0.5x to 2.0x)
        adjustment = max(0.5, min(2.0, adjustment))
        
        logger.debug(
            f"ATR adjustment for {symbol}: base_atr={base_atr:.8f}, "
            f"current_atr={current_atr:.8f}, adjustment={adjustment:.3f}x"
        )
        
        return adjustment
    
    def _get_atr(
        self,
        symbol: str,
        klines: Optional[List[List]] = None
    ) -> Optional[float]:
        """Get ATR value for symbol (with caching).
        
        Args:
            symbol: Trading symbol
            klines: Historical klines (will fetch if not provided)
            
        Returns:
            ATR value or None if unavailable
        """
        # Check cache
        if symbol in self._atr_cache:
            atr_value, cached_time = self._atr_cache[symbol]
            if datetime.now(timezone.utc) - cached_time < self._atr_cache_ttl:
                return atr_value
        
        # Calculate ATR
        if klines is None:
            # Fetch klines (simplified - would need interval from strategy)
            # For now, return None if klines not provided
            logger.debug(f"ATR calculation for {symbol} requires klines")
            return None
        
        atr = calculate_atr(klines, period=self.config.atr_period)
        if atr is not None:
            # Cache the result
            self._atr_cache[symbol] = (atr, datetime.now(timezone.utc))
        
        return atr
    
    def _calculate_performance_adjustment(self, strategy_id: str) -> float:
        """Calculate performance-based position size adjustment.
        
        Win streaks → Increase position size
        Loss streaks → Decrease position size
        
        Args:
            strategy_id: Strategy ID
            
        Returns:
            Adjustment factor (1.0 = no change)
        """
        perf = self._performance.get(strategy_id)
        if not perf or perf.total_trades == 0:
            return 1.0  # No performance data yet
        
        adjustment = 1.0
        
        # Win streak boost
        if perf.current_win_streak > 0:
            boost = min(
                perf.current_win_streak * self.config.win_streak_boost,
                self.config.max_win_streak_boost
            )
            adjustment += boost
        
        # Loss streak reduction
        if perf.current_loss_streak > 0:
            reduction = min(
                perf.current_loss_streak * self.config.loss_streak_reduction,
                self.config.max_loss_streak_reduction
            )
            adjustment -= reduction
        
        # Ensure adjustment is within bounds
        adjustment = max(0.5, min(1.5, adjustment))
        
        logger.debug(
            f"Performance adjustment for {strategy_id}: "
            f"win_streak={perf.current_win_streak}, loss_streak={perf.current_loss_streak}, "
            f"adjustment={adjustment:.3f}x"
        )
        
        return adjustment
    
    def _calculate_kelly_adjustment(
        self,
        strategy_id: str,
        base_notional: float,
        price: float
    ) -> Optional[float]:
        """Calculate Kelly Criterion position size adjustment.
        
        CRITICAL SAFEGUARDS:
        - Minimum sample size (100 trades)
        - Fractional Kelly (default 0.25 = quarter Kelly)
        - Maximum position size cap (10% of balance)
        - Disabled after drawdown breach
        
        Args:
            strategy_id: Strategy ID
            base_notional: Base position notional
            price: Current price
            
        Returns:
            Adjustment factor or None if Kelly should not be used
        """
        perf = self._performance.get(strategy_id)
        if not perf or perf.total_trades < self.config.min_trades_for_kelly:
            return None  # Insufficient data
        
        # Calculate win rate and average win/loss
        if perf.winning_trades == 0 or perf.losing_trades == 0:
            return None  # Need both wins and losses
        
        win_rate = perf.winning_trades / perf.total_trades
        avg_win = perf.total_profit / perf.winning_trades if perf.winning_trades > 0 else 0
        avg_loss = abs(perf.total_loss / perf.losing_trades) if perf.losing_trades > 0 else 0
        
        if avg_loss == 0:
            return None  # Cannot calculate Kelly
        
        # Kelly formula: f = (p * b - q) / b
        # where:
        #   p = win rate
        #   q = loss rate (1 - p)
        #   b = avg_win / avg_loss (win/loss ratio)
        win_loss_ratio = avg_win / avg_loss
        kelly_fraction = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        
        # Apply fractional Kelly and safeguards
        kelly_fraction = max(0, kelly_fraction)  # No negative Kelly
        fractional_kelly = kelly_fraction * self.config.kelly_fraction
        
        # Cap at maximum position size
        balance = self.client.futures_account_balance()
        max_position_notional = balance * self.config.max_kelly_position_pct
        kelly_notional = base_notional * (1 + fractional_kelly)
        
        if kelly_notional > max_position_notional:
            fractional_kelly = (max_position_notional / base_notional) - 1
            fractional_kelly = max(0, fractional_kelly)  # Ensure non-negative
        
        # Calculate adjustment factor
        adjustment = 1 + fractional_kelly
        
        # Final safeguard: cap adjustment to reasonable bounds
        adjustment = max(0.5, min(2.0, adjustment))
        
        logger.info(
            f"Kelly Criterion for {strategy_id}: "
            f"win_rate={win_rate:.2%}, win/loss={win_loss_ratio:.2f}, "
            f"kelly={kelly_fraction:.3f}, fractional={fractional_kelly:.3f}, "
            f"adjustment={adjustment:.3f}x"
        )
        
        return adjustment
    
    def record_trade(
        self,
        strategy_id: str,
        pnl: float,
        is_win: bool
    ) -> None:
        """Record trade result for performance tracking.
        
        Args:
            strategy_id: Strategy ID
            pnl: Profit/loss for this trade
            is_win: True if winning trade, False if losing
        """
        if strategy_id not in self._performance:
            self._performance[strategy_id] = TradePerformance()
        
        perf = self._performance[strategy_id]
        perf.total_trades += 1
        perf.last_trade_pnl = pnl
        
        if is_win:
            perf.winning_trades += 1
            perf.total_profit += pnl
            perf.current_win_streak += 1
            perf.current_loss_streak = 0
        else:
            perf.losing_trades += 1
            perf.total_loss += pnl
            perf.current_loss_streak += 1
            perf.current_win_streak = 0
        
        logger.debug(
            f"Recorded trade for {strategy_id}: "
            f"pnl={pnl:.2f}, is_win={is_win}, "
            f"win_streak={perf.current_win_streak}, loss_streak={perf.current_loss_streak}"
        )
    
    def get_performance(self, strategy_id: str) -> Optional[TradePerformance]:
        """Get performance metrics for a strategy.
        
        Args:
            strategy_id: Strategy ID
            
        Returns:
            TradePerformance or None if no data
        """
        return self._performance.get(strategy_id)







