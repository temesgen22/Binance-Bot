"""
Utility functions for backtesting parameter extraction and calculations.
Reduces code duplication across backtesting code.
"""
from typing import Dict, Any, Optional


def extract_range_mean_reversion_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize parameters for range mean reversion strategy.
    
    Args:
        params: Strategy parameters dictionary
        
    Returns:
        Dictionary with normalized parameter values
    """
    return {
        "lookback_period": int(params.get("lookback_period", 150)),
        "ema_slow_period": int(params.get("ema_slow_period", 50)),
        "rsi_period": int(params.get("rsi_period", 14)),
        "ema_fast_period": int(params.get("ema_fast_period", 20)),
        "buy_zone_pct": float(params.get("buy_zone_pct", 0.2)),
        "sell_zone_pct": float(params.get("sell_zone_pct", 0.2)),
        "tp_buffer_pct": float(params.get("tp_buffer_pct", 0.001)),
        "sl_buffer_pct": float(params.get("sl_buffer_pct", 0.002)),
        "rsi_oversold": float(params.get("rsi_oversold", 40)),
        "rsi_overbought": float(params.get("rsi_overbought", 60)),
        "max_ema_spread_pct": float(params.get("max_ema_spread_pct", 0.005)),
    }


def extract_scalping_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize parameters for scalping strategy.
    
    Args:
        params: Strategy parameters dictionary
        
    Returns:
        Dictionary with normalized parameter values
    """
    return {
        "ema_fast": int(params.get("ema_fast", 8)),
        "ema_slow": int(params.get("ema_slow", 21)),
        "take_profit_pct": float(params.get("take_profit_pct", 0.004)),
        "stop_loss_pct": float(params.get("stop_loss_pct", 0.002)),
        "trailing_stop_enabled": params.get("trailing_stop_enabled", False),
    }


def calculate_tp_sl_levels(
    entry_price: float,
    position_side: str,
    take_profit_pct: float,
    stop_loss_pct: float
) -> Dict[str, float]:
    """
    Calculate take profit and stop loss levels for a position.
    
    Args:
        entry_price: Entry price of the position
        position_side: "LONG" or "SHORT"
        take_profit_pct: Take profit percentage (e.g., 0.004 for 0.4%)
        stop_loss_pct: Stop loss percentage (e.g., 0.002 for 0.2%)
        
    Returns:
        Dictionary with "take_profit" and "stop_loss" keys
    """
    if position_side == "LONG":
        take_profit = entry_price * (1 + take_profit_pct)
        stop_loss = entry_price * (1 - stop_loss_pct)
    elif position_side == "SHORT":
        take_profit = entry_price * (1 - take_profit_pct)  # Inverted for shorts
        stop_loss = entry_price * (1 + stop_loss_pct)  # Inverted for shorts
    else:
        raise ValueError(f"Invalid position_side: {position_side}. Must be 'LONG' or 'SHORT'")
    
    return {
        "take_profit": take_profit,
        "stop_loss": stop_loss
    }


def calculate_range_tp_sl_levels(
    range_high: float,
    range_low: float,
    range_mid: float,
    position_side: str,
    tp_buffer_pct: float,
    sl_buffer_pct: float
) -> Dict[str, Optional[float]]:
    """
    Calculate TP/SL levels for range mean reversion strategy.
    
    Args:
        range_high: Range high price
        range_low: Range low price
        range_mid: Range midpoint price
        position_side: "LONG" or "SHORT"
        tp_buffer_pct: Take profit buffer percentage
        sl_buffer_pct: Stop loss buffer percentage
        
    Returns:
        Dictionary with "tp1", "tp2", and "sl" keys
    """
    range_size = range_high - range_low
    
    if position_side == "LONG":
        tp1 = range_mid
        tp2 = range_high - (range_size * tp_buffer_pct)
        sl = range_low - (range_size * sl_buffer_pct)
    elif position_side == "SHORT":
        tp1 = range_mid
        tp2 = range_low + (range_size * tp_buffer_pct)
        sl = range_high + (range_size * sl_buffer_pct)
    else:
        return {"tp1": None, "tp2": None, "sl": None}
    
    return {
        "tp1": tp1,
        "tp2": tp2,
        "sl": sl
    }



