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


def calculate_market_structure(
    highs: list[float],
    lows: list[float],
    swing_period: int = 5
) -> Optional[dict]:
    """
    Calculate Market Structure (HH/HL or LH/LL).
    
    Market Structure identifies trend direction by analyzing swing highs and swing lows:
    - HH/HL (Higher High / Higher Low): Bullish structure (uptrend)
    - LH/LL (Lower High / Lower Low): Bearish structure (downtrend)
    
    Args:
        highs: List of high prices (most recent last)
        lows: List of low prices (most recent last)
        swing_period: Number of candles to look back/forward to identify swing points (default 5)
    
    Returns:
        Dictionary with market structure information:
        {
            "structure": "BULLISH" | "BEARISH" | "NEUTRAL" | None,
            "last_swing_high": float | None,
            "last_swing_low": float | None,
            "previous_swing_high": float | None,
            "previous_swing_low": float | None,
            "has_higher_high": bool | None,
            "has_higher_low": bool | None,
            "has_lower_high": bool | None,
            "has_lower_low": bool | None,
            "swing_highs": list[tuple[int, float]],  # (index, price)
            "swing_lows": list[tuple[int, float]]     # (index, price)
        }
        or None if insufficient data
    
    Example:
        >>> highs = [100, 102, 101, 103, 105, 104, 106, 105, 107]
        >>> lows = [99, 100, 100, 101, 103, 103, 104, 104, 105]
        >>> structure = calculate_market_structure(highs, lows, swing_period=3)
    """
    if len(highs) < swing_period * 2 + 1 or len(lows) < swing_period * 2 + 1:
        return None  # Need enough data to identify swing points
    
    if len(highs) != len(lows):
        return None  # Highs and lows must have same length
    
    # Find swing highs and swing lows
    # A swing high is a high that is higher than N candles before and after
    # A swing low is a low that is lower than N candles before and after
    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []
    
    # Check for swing points (excluding edges where we can't check both sides)
    for i in range(swing_period, len(highs) - swing_period):
        # Check if this is a swing high
        is_swing_high = True
        current_high = highs[i]
        for j in range(i - swing_period, i + swing_period + 1):
            if j != i and highs[j] >= current_high:
                is_swing_high = False
                break
        
        if is_swing_high:
            swing_highs.append((i, current_high))
        
        # Check if this is a swing low
        is_swing_low = True
        current_low = lows[i]
        for j in range(i - swing_period, i + swing_period + 1):
            if j != i and lows[j] <= current_low:
                is_swing_low = False
                break
        
        if is_swing_low:
            swing_lows.append((i, current_low))
    
    # Need at least 2 swing highs and 2 swing lows to determine structure
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return {
            "structure": "NEUTRAL",
            "last_swing_high": swing_highs[-1][1] if swing_highs else None,
            "last_swing_low": swing_lows[-1][1] if swing_lows else None,
            "previous_swing_high": swing_highs[-2][1] if len(swing_highs) >= 2 else None,
            "previous_swing_low": swing_lows[-2][1] if len(swing_lows) >= 2 else None,
            "has_higher_high": None,
            "has_higher_low": None,
            "has_lower_high": None,
            "has_lower_low": None,
            "swing_highs": swing_highs,
            "swing_lows": swing_lows,
        }
    
    # Get the last two swing highs and swing lows
    last_swing_high = swing_highs[-1][1]
    previous_swing_high = swing_highs[-2][1]
    last_swing_low = swing_lows[-1][1]
    previous_swing_low = swing_lows[-2][1]
    
    # Determine market structure
    has_higher_high = last_swing_high > previous_swing_high
    has_higher_low = last_swing_low > previous_swing_low
    has_lower_high = last_swing_high < previous_swing_high
    has_lower_low = last_swing_low < previous_swing_low
    
    # Market structure determination:
    # BULLISH: HH (Higher High) AND HL (Higher Low)
    # BEARISH: LH (Lower High) AND LL (Lower Low)
    # NEUTRAL: Mixed signals or unclear
    
    structure = "NEUTRAL"
    if has_higher_high and has_higher_low:
        structure = "BULLISH"  # HH/HL pattern
    elif has_lower_high and has_lower_low:
        structure = "BEARISH"  # LH/LL pattern
    elif has_higher_high and not has_lower_low:
        # Higher high but not lower low (could be bullish continuation)
        structure = "BULLISH"
    elif has_lower_low and not has_higher_high:
        # Lower low but not higher high (could be bearish continuation)
        structure = "BEARISH"
    
    return {
        "structure": structure,
        "last_swing_high": last_swing_high,
        "last_swing_low": last_swing_low,
        "previous_swing_high": previous_swing_high,
        "previous_swing_low": previous_swing_low,
        "has_higher_high": has_higher_high,
        "has_higher_low": has_higher_low,
        "has_lower_high": has_lower_high,
        "has_lower_low": has_lower_low,
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
    }


def calculate_volume_ema(volumes: list[float], period: int) -> Optional[float]:
    """
    Calculate Volume EMA (Exponential Moving Average of volume).
    
    Volume EMA helps identify if current volume is above or below average,
    which can confirm price movements.
    
    Args:
        volumes: List of volume values (most recent last)
        period: EMA period (default 20)
    
    Returns:
        Volume EMA value or None if insufficient data
    
    Example:
        >>> volumes = [1000, 1200, 1100, 1300, 1500, 1400]
        >>> volume_ema = calculate_volume_ema(volumes, period=3)
    """
    if len(volumes) < period:
        return None
    
    smoothing = 2.0 / (period + 1)
    ema = fmean(volumes[:period])
    
    for v in volumes[period:]:
        ema = (v - ema) * smoothing + ema
    
    return ema


def calculate_volume_analysis(klines: list[list], period: int = 20) -> Optional[dict]:
    """
    Calculate comprehensive volume analysis.
    
    Provides volume metrics including:
    - Average volume
    - Current volume vs average
    - Volume trend (increasing/decreasing)
    - Volume EMA
    
    Args:
        klines: List of kline/candlestick data
               Format: [open_time, open, high, low, close, volume, close_time, ...]
        period: Period for volume analysis (default 20)
    
    Returns:
        Dictionary with volume analysis:
        {
            "current_volume": float,
            "average_volume": float,
            "volume_ema": float,
            "volume_ratio": float,  # current / average
            "volume_trend": "INCREASING" | "DECREASING" | "STABLE",
            "volume_change_pct": float,  # % change from previous period
            "is_high_volume": bool,  # True if current > 1.5x average
            "is_low_volume": bool,   # True if current < 0.5x average
        }
        or None if insufficient data
    
    Example:
        >>> klines = [
        ...     [0, 100, 102, 99, 101, 1000, 60000],
        ...     [60000, 101, 103, 100, 102, 1200, 120000]
        ... ]
        >>> volume_analysis = calculate_volume_analysis(klines, period=2)
    """
    if len(klines) < period + 1:
        return None
    
    # Extract volumes (index 5 in kline structure)
    volumes = [float(k[5]) for k in klines]
    
    # Get recent volumes for analysis
    recent_volumes = volumes[-period:] if len(volumes) >= period else volumes
    current_volume = volumes[-1] if volumes else None
    
    if current_volume is None or len(recent_volumes) < period:
        return None
    
    # Calculate average volume
    average_volume = fmean(recent_volumes)
    
    # Calculate Volume EMA
    volume_ema = calculate_volume_ema(recent_volumes, period=min(period, len(recent_volumes)))
    
    # Calculate volume ratio (current vs average)
    volume_ratio = current_volume / average_volume if average_volume > 0 else 1.0
    
    # Calculate volume trend (compare last period to previous period)
    volume_trend = "STABLE"
    volume_change_pct = 0.0
    if len(volumes) >= period * 2:
        previous_period_avg = fmean(volumes[-period * 2:-period])
        current_period_avg = fmean(recent_volumes)
        if previous_period_avg > 0:
            volume_change_pct = ((current_period_avg - previous_period_avg) / previous_period_avg) * 100
            if volume_change_pct > 5:
                volume_trend = "INCREASING"
            elif volume_change_pct < -5:
                volume_trend = "DECREASING"
    
    # Determine if volume is high or low
    is_high_volume = volume_ratio > 1.5  # 50% above average
    is_low_volume = volume_ratio < 0.5   # 50% below average
    
    return {
        "current_volume": current_volume,
        "average_volume": average_volume,
        "volume_ema": volume_ema,
        "volume_ratio": volume_ratio,
        "volume_trend": volume_trend,
        "volume_change_pct": volume_change_pct,
        "is_high_volume": is_high_volume,
        "is_low_volume": is_low_volume,
    }