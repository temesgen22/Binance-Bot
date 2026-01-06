"""
Correlation-based risk management for portfolio diversification.

Phase 3 Week 6: Correlation & Margin Protection
- Rolling correlation calculation (return-based, not price-based)
- Correlation-based exposure limits
- Minimum data threshold
- Hourly cache refresh
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from loguru import logger

from app.core.exceptions import RiskLimitExceededError

# Try to import numpy, fall back to pure Python if not available
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


@dataclass
class CorrelationPair:
    """Correlation data for a symbol pair."""
    symbol1: str
    symbol2: str
    correlation: float  # -1.0 to 1.0
    window_days: int
    data_points: int
    calculated_at: datetime


@dataclass
class CorrelationGroup:
    """Group of symbols with high correlation."""
    symbols: List[str]
    avg_correlation: float
    max_correlation: float
    group_id: str


class CorrelationManager:
    """Manages correlation calculations and exposure limits.
    
    CRITICAL REQUIREMENTS:
    - Rolling correlation (30-90 day window, configurable)
    - Return-based (not price-based)
    - Minimum data threshold (20+ points)
    - Hourly cache refresh
    - Pearson correlation coefficient
    """
    
    def __init__(
        self,
        window_days: int = 30,
        min_data_points: int = 20,
        cache_ttl_hours: int = 1,
        max_correlation_exposure_pct: float = 0.5,  # 50% max exposure for correlated symbols
    ):
        """Initialize correlation manager.
        
        Args:
            window_days: Rolling window in days (default 30)
            min_data_points: Minimum data points required (default 20)
            cache_ttl_hours: Cache TTL in hours (default 1)
            max_correlation_exposure_pct: Max exposure % for correlated symbols (default 0.5)
        """
        self.window_days = window_days
        self.min_data_points = min_data_points
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.max_correlation_exposure_pct = max_correlation_exposure_pct
        
        # Cache: {symbol_pair_key: (correlation, calculated_at)}
        self._correlation_cache: Dict[str, Tuple[float, datetime]] = {}
        
        # Correlation groups: {group_id: CorrelationGroup}
        self._correlation_groups: Dict[str, CorrelationGroup] = {}
        
        # Price history cache: {symbol: [(timestamp, price), ...]}
        self._price_history: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
    
    def calculate_correlation(
        self,
        symbol1: str,
        symbol2: str,
        price_history1: List[Tuple[datetime, float]],
        price_history2: List[Tuple[datetime, float]],
        force_recalculate: bool = False
    ) -> Optional[CorrelationPair]:
        """Calculate rolling correlation between two symbols.
        
        CRITICAL: Uses return-based correlation, not price-based.
        
        Args:
            symbol1: First symbol
            symbol2: Second symbol
            price_history1: Price history for symbol1 [(timestamp, price), ...]
            price_history2: Price history for symbol2 [(timestamp, price), ...]
            force_recalculate: Force recalculation even if cached
            
        Returns:
            CorrelationPair or None if insufficient data
        """
        # Check cache first
        cache_key = self._get_cache_key(symbol1, symbol2)
        if not force_recalculate and cache_key in self._correlation_cache:
            correlation, cached_at = self._correlation_cache[cache_key]
            if datetime.now(timezone.utc) - cached_at < self.cache_ttl:
                return CorrelationPair(
                    symbol1=symbol1,
                    symbol2=symbol2,
                    correlation=correlation,
                    window_days=self.window_days,
                    data_points=0,  # Will be calculated below
                    calculated_at=cached_at
                )
        
        # Filter to rolling window
        window_start = datetime.now(timezone.utc) - timedelta(days=self.window_days)
        
        # Align price histories by timestamp
        aligned_prices = self._align_price_histories(
            price_history1,
            price_history2,
            window_start
        )
        
        if len(aligned_prices) < self.min_data_points:
            logger.debug(
                f"Insufficient data for correlation {symbol1}-{symbol2}: "
                f"{len(aligned_prices)} points (min: {self.min_data_points})"
            )
            return None
        
        # Calculate returns (CRITICAL: return-based, not price-based)
        returns1 = []
        returns2 = []
        
        for i in range(1, len(aligned_prices)):
            price1_prev, price1_curr = aligned_prices[i-1][1], aligned_prices[i][1]
            price2_prev, price2_curr = aligned_prices[i-1][2], aligned_prices[i][2]
            
            # Calculate return: (current - previous) / previous
            if price1_prev > 0:
                return1 = (price1_curr - price1_prev) / price1_prev
                returns1.append(return1)
            else:
                continue
            
            if price2_prev > 0:
                return2 = (price2_curr - price2_prev) / price2_prev
                returns2.append(return2)
            else:
                continue
        
        # Ensure same length
        min_len = min(len(returns1), len(returns2))
        if min_len < self.min_data_points:
            logger.debug(
                f"Insufficient returns for correlation {symbol1}-{symbol2}: "
                f"{min_len} points (min: {self.min_data_points})"
            )
            return None
        
        returns1 = returns1[:min_len]
        returns2 = returns2[:min_len]
        
        # Calculate Pearson correlation coefficient
        try:
            if HAS_NUMPY:
                correlation = np.corrcoef(returns1, returns2)[0, 1]
                # Handle NaN (can occur if all returns are identical)
                if np.isnan(correlation):
                    correlation = 0.0
            else:
                # Pure Python Pearson correlation
                correlation = self._pearson_correlation(returns1, returns2)
        except Exception as e:
            logger.warning(f"Error calculating correlation {symbol1}-{symbol2}: {e}")
            return None
        
        # Cache the result
        self._correlation_cache[cache_key] = (correlation, datetime.now(timezone.utc))
        
        return CorrelationPair(
            symbol1=symbol1,
            symbol2=symbol2,
            correlation=correlation,
            window_days=self.window_days,
            data_points=min_len,
            calculated_at=datetime.now(timezone.utc)
        )
    
    def _align_price_histories(
        self,
        history1: List[Tuple[datetime, float]],
        history2: List[Tuple[datetime, float]],
        window_start: datetime
    ) -> List[Tuple[datetime, float, float]]:
        """Align two price histories by timestamp.
        
        Returns:
            List of (timestamp, price1, price2) tuples
        """
        # Filter to window and sort by timestamp
        filtered1 = [
            (ts, price) for ts, price in history1
            if ts >= window_start
        ]
        filtered2 = [
            (ts, price) for ts, price in history2
            if ts >= window_start
        ]
        
        filtered1.sort(key=lambda x: x[0])
        filtered2.sort(key=lambda x: x[0])
        
        # Align by timestamp (use closest match within 1 hour)
        aligned = []
        i, j = 0, 0
        
        while i < len(filtered1) and j < len(filtered2):
            ts1, price1 = filtered1[i]
            ts2, price2 = filtered2[j]
            
            # Check if timestamps are close (within 1 hour)
            time_diff = abs((ts1 - ts2).total_seconds())
            
            if time_diff < 3600:  # Within 1 hour
                aligned.append((ts1, price1, price2))
                i += 1
                j += 1
            elif ts1 < ts2:
                i += 1
            else:
                j += 1
        
        return aligned
    
    def _get_cache_key(self, symbol1: str, symbol2: str) -> str:
        """Get cache key for symbol pair (sorted to ensure consistency)."""
        return f"{min(symbol1, symbol2)}:{max(symbol1, symbol2)}"
    
    def get_correlation_groups(
        self,
        symbols: List[str],
        correlation_threshold: float = 0.7,
        price_histories: Optional[Dict[str, List[Tuple[datetime, float]]]] = None
    ) -> List[CorrelationGroup]:
        """Group symbols by correlation.
        
        Args:
            symbols: List of symbols to analyze
            correlation_threshold: Minimum correlation to group (default 0.7)
            price_histories: Price histories for symbols (optional, will use cache if not provided)
            
        Returns:
            List of correlation groups
        """
        if price_histories is None:
            price_histories = self._price_history
        
        groups = []
        processed = set()
        
        for i, symbol1 in enumerate(symbols):
            if symbol1 in processed:
                continue
            
            group_symbols = [symbol1]
            correlations = []
            
            for symbol2 in symbols[i+1:]:
                if symbol2 in processed:
                    continue
                
                # Get price histories
                hist1 = price_histories.get(symbol1, [])
                hist2 = price_histories.get(symbol2, [])
                
                if not hist1 or not hist2:
                    continue
                
                # Calculate correlation
                corr_pair = self.calculate_correlation(symbol1, symbol2, hist1, hist2)
                
                if corr_pair and corr_pair.correlation >= correlation_threshold:
                    group_symbols.append(symbol2)
                    correlations.append(corr_pair.correlation)
            
            if len(group_symbols) > 1:
                # Calculate average correlation (fallback to pure Python if numpy not available)
                if correlations:
                    if HAS_NUMPY:
                        avg_corr = float(np.mean(correlations))
                    else:
                        avg_corr = sum(correlations) / len(correlations)
                    max_corr = max(correlations)
                else:
                    avg_corr = 0.0
                    max_corr = 0.0
                
                group = CorrelationGroup(
                    symbols=group_symbols,
                    avg_correlation=avg_corr,
                    max_correlation=max_corr,
                    group_id=f"group_{len(groups)}"
                )
                groups.append(group)
                
                # Mark symbols as processed
                processed.update(group_symbols)
        
        return groups
    
    def check_correlation_exposure(
        self,
        symbol: str,
        current_exposure: float,
        total_exposure: float,
        account_balance: float,
        price_histories: Optional[Dict[str, List[Tuple[datetime, float]]]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Check if adding exposure to symbol would breach correlation limits.
        
        Args:
            symbol: Symbol to check
            current_exposure: Current exposure for this symbol
            total_exposure: Total portfolio exposure
            account_balance: Account balance
            price_histories: Price histories (optional)
            
        Returns:
            (allowed, reason) tuple
        """
        if price_histories is None:
            price_histories = self._price_history
        
        # Get all symbols with positions
        # For now, we'll check against all symbols in price history
        # In production, this would come from active positions
        active_symbols = list(price_histories.keys())
        
        if symbol not in active_symbols:
            # New symbol, no correlation check needed yet
            return True, None
        
        # Find correlation group for this symbol
        groups = self.get_correlation_groups(active_symbols + [symbol], price_histories=price_histories)
        
        for group in groups:
            if symbol in group.symbols:
                # Calculate total exposure for this correlation group
                group_exposure = 0.0
                for group_symbol in group.symbols:
                    # In production, get actual exposure for each symbol
                    # For now, assume all symbols in group have equal exposure
                    if group_symbol == symbol:
                        group_exposure += current_exposure
                    else:
                        # Estimate exposure (would be actual in production)
                        group_exposure += current_exposure  # Simplified
                
                # Check if group exposure exceeds limit
                max_group_exposure = account_balance * self.max_correlation_exposure_pct
                
                if group_exposure > max_group_exposure:
                    return False, (
                        f"Correlation group exposure limit exceeded: "
                        f"{group_exposure:.2f} USDT > {max_group_exposure:.2f} USDT "
                        f"(group: {', '.join(group.symbols)}, correlation: {group.avg_correlation:.2f})"
                    )
        
        return True, None
    
    def update_price_history(
        self,
        symbol: str,
        price: float,
        timestamp: Optional[datetime] = None
    ) -> None:
        """Update price history for a symbol.
        
        Args:
            symbol: Trading symbol
            price: Current price
            timestamp: Timestamp (default: now)
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        # Add to history
        self._price_history[symbol].append((timestamp, price))
        
        # Keep only last window_days + buffer
        window_start = datetime.now(timezone.utc) - timedelta(days=self.window_days + 7)
        self._price_history[symbol] = [
            (ts, p) for ts, p in self._price_history[symbol]
            if ts >= window_start
        ]
        
        # Sort by timestamp
        self._price_history[symbol].sort(key=lambda x: x[0])
    
    def _pearson_correlation(self, x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient (pure Python).
        
        Args:
            x: First data series
            y: Second data series
            
        Returns:
            Correlation coefficient (-1.0 to 1.0)
        """
        n = len(x)
        if n != len(y) or n == 0:
            return 0.0
        
        # Calculate means
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        # Calculate numerator and denominators
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        sum_sq_x = sum((x[i] - mean_x) ** 2 for i in range(n))
        sum_sq_y = sum((y[i] - mean_y) ** 2 for i in range(n))
        
        # Calculate correlation
        denominator = (sum_sq_x * sum_sq_y) ** 0.5
        
        if denominator == 0:
            return 0.0
        
        correlation = numerator / denominator
        
        # Clamp to [-1, 1] (should already be, but safety check)
        return max(-1.0, min(1.0, correlation))
    
    def clear_cache(self) -> None:
        """Clear correlation cache."""
        self._correlation_cache.clear()
        logger.info("Correlation cache cleared")

