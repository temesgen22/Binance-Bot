"""
Shared technical indicator functions for strategies.
These utilities can be reused across different strategy implementations.
"""
from __future__ import annotations

from typing import Optional
from statistics import fmean


def calculate_ema(prices: list[float], period: int) -> Optional[float]:
    """
    Calculate Exponential Moving Average (EMA) from a list of prices.
    
    This uses the standard EMA formula:
    - Seeds with SMA(period) for first value
    - Then iterates forward with EMA smoothing: EMA = (Price - EMA) * multiplier + EMA
    
    Args:
        prices: List of prices (most recent last)
        period: EMA period
    
    Returns:
        EMA value or None if insufficient data
        
    Example:
        >>> prices = [100, 102, 101, 103, 105, 104]
        >>> ema = calculate_ema(prices, period=3)
    """
    if len(prices) < period:
        return None  # Insufficient data - return None for safety
    
    smoothing = 2.0 / (period + 1)
    # Start with SMA (Simple Moving Average) for the first value as seed
    # This is the standard EMA initialization method
    ema = fmean(prices[:period])
    
    # Calculate EMA for remaining prices using standard EMA update formula:
    # EMA = (Price - EMA) * multiplier + EMA
    for p in prices[period:]:
        ema = (p - ema) * smoothing + ema
    
    return ema


def calculate_rsi(prices: list[float], period: int = 14) -> Optional[float]:
    """
    Calculate Relative Strength Index (RSI).
    
    RSI measures momentum on a scale of 0-100:
    - RSI < 30: Oversold (potential buy signal)
    - RSI > 70: Overbought (potential sell signal)
    - RSI 40-60: Neutral zone
    
    Args:
        prices: List of closing prices (most recent last)
        period: RSI period (default 14)
    
    Returns:
        RSI value between 0-100, or None if insufficient data
        
    Example:
        >>> prices = [100, 102, 101, 103, 105, 104, 106, 105, 107, 108, 107, 109, 110, 109, 111, 110]
        >>> rsi = calculate_rsi(prices, period=14)
    """
    if len(prices) < period + 1:
        return None  # Need at least period+1 prices to calculate period deltas
    
    # Calculate price changes over the period
    # For len(prices) = period + 1, loop starts at i = 1 and ends at i = period
    # This gives exactly period deltas, which is correct
    deltas = []
    for i in range(len(prices) - period, len(prices)):
        if i > 0:  # Can't calculate delta for first price
            deltas.append(prices[i] - prices[i - 1])
    
    # Separate gains and losses
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    
    # Calculate average gain and loss using simple mean
    # Note: This is a simplified RSI (not Wilder's smoothing) but works well for our use case
    avg_gain = fmean(gains) if gains else 0.0
    avg_loss = fmean(losses) if losses else 0.0
    
    # Avoid division by zero - handle edge cases
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0  # All gains or all flat
    
    # Calculate RS (Relative Strength) and RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_atr(klines: list[list], period: int = 14) -> Optional[float]:
    """
    Calculate Average True Range (ATR) - a volatility indicator.
    
    ATR measures market volatility by averaging true range over a period.
    True Range = max of:
    - High - Low
    - abs(High - Previous Close)
    - abs(Low - Previous Close)
    
    Args:
        klines: List of kline/candlestick data
               Format: [open_time, open, high, low, close, volume, close_time, ...]
        period: ATR period (default 14)
    
    Returns:
        ATR value or None if insufficient data
        
    Example:
        >>> klines = [
        ...     [0, 100, 102, 99, 101, 1000, 60000],  # prev candle
        ...     [60000, 101, 103, 100, 102, 1100, 120000]  # current candle
        ... ]
        >>> atr = calculate_atr(klines, period=2)
    """
    if len(klines) < period + 1:
        return None  # Need at least period+1 klines to calculate period TR values
    
    true_ranges = []
    # Calculate True Range for the last 'period' candles
    # Since we require len(klines) >= period + 1, the smallest i in loop is >= 1
    # Therefore the else branch (for i == 0) is dead code, but kept for safety
    for i in range(len(klines) - period, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        
        if i > 0:
            # True Range = max of:
            # - Current high - low
            # - abs(Current high - Previous close)  [accounts for gaps]
            # - abs(Current low - Previous close)   [accounts for gaps]
            prev_close = float(klines[i - 1][4])
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
        else:
            # Fallback for first candle (shouldn't execute due to len check above)
            tr = high - low
        
        true_ranges.append(tr)
    
    # Calculate average of True Ranges (we get exactly 'period' values)
    return fmean(true_ranges) if true_ranges else None

