"""
Utility functions for backtesting parameter extraction and calculations.
Reduces code duplication across backtesting code.
"""
from typing import Dict, Any, Optional


def _num(value: Any, default: Any, cast: type = float):
    """Return cast(value) or default when value is None (e.g. JSON null)."""
    if value is None:
        return default
    return cast(value)


def _bool_param(value: Any, default: bool) -> bool:
    """Parse bool like Strategy.parse_bool_param — bool('false') must not be True."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        v = value.lower().strip()
        if v in ("true", "1", "yes", "on", "enabled"):
            return True
        if v in ("false", "0", "no", "off", "disabled", ""):
            return False
        return default
    return bool(value)


def extract_range_mean_reversion_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize parameters for range mean reversion strategy.
    
    Args:
        params: Strategy parameters dictionary
        
    Returns:
        Dictionary with normalized parameter values
    """
    return {
        "lookback_period": _num(params.get("lookback_period"), 150, int),
        "ema_slow_period": _num(params.get("ema_slow_period"), 50, int),
        "rsi_period": _num(params.get("rsi_period"), 14, int),
        "ema_fast_period": _num(params.get("ema_fast_period"), 20, int),
        "buy_zone_pct": _num(params.get("buy_zone_pct"), 0.2),
        "sell_zone_pct": _num(params.get("sell_zone_pct"), 0.2),
        "tp_buffer_pct": _num(params.get("tp_buffer_pct"), 0.001),
        "sl_buffer_pct": _num(params.get("sl_buffer_pct"), 0.002),
        "rsi_oversold": _num(params.get("rsi_oversold"), 40),
        "rsi_overbought": _num(params.get("rsi_overbought"), 60),
        "max_ema_spread_pct": _num(params.get("max_ema_spread_pct"), 0.005),
        "sl_trigger_mode": str(params.get("sl_trigger_mode", "live_price")).lower()
        if str(params.get("sl_trigger_mode", "live_price")).lower() in ("live_price", "candle_close")
        else "live_price",
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
        "ema_fast": _num(params.get("ema_fast"), 8, int),
        "ema_slow": _num(params.get("ema_slow"), 21, int),
        "take_profit_pct": _num(params.get("take_profit_pct"), 0.004),
        "stop_loss_pct": _num(params.get("stop_loss_pct"), 0.002),
        # Use same semantics as Strategy.parse_bool_param (bool("false") must be False, not True)
        "use_rsi_filter": _bool_param(params.get("use_rsi_filter"), False),
        "rsi_period": _num(params.get("rsi_period"), 14, int),
        "rsi_long_min": _num(params.get("rsi_long_min"), 50.0),
        "rsi_short_max": _num(params.get("rsi_short_max"), 50.0),
        "use_atr_filter": _bool_param(params.get("use_atr_filter"), False),
        "atr_period": _num(params.get("atr_period"), 14, int),
        "atr_min_pct": _num(params.get("atr_min_pct"), 0.0),
        "atr_max_pct": _num(params.get("atr_max_pct"), 100.0),
        "use_volume_filter": _bool_param(params.get("use_volume_filter"), False),
        "volume_ma_period": _num(params.get("volume_ma_period"), 20, int),
        "volume_multiplier_min": _num(params.get("volume_multiplier_min"), 1.0),
        "use_structure_filter": _bool_param(params.get("use_structure_filter"), False),
        "structure_left_bars": _num(params.get("structure_left_bars"), 2, int),
        "structure_right_bars": _num(params.get("structure_right_bars"), 2, int),
        "structure_confirm_on_close": _bool_param(params.get("structure_confirm_on_close"), True),
        "trailing_stop_enabled": _bool_param(params.get("trailing_stop_enabled"), False),
        "trailing_stop_activation_pct": _num(params.get("trailing_stop_activation_pct"), 0.0),
        "pnl_giveback_enabled": _bool_param(params.get("pnl_giveback_enabled"), False),
        "pnl_giveback_from_peak_usdt": _num(params.get("pnl_giveback_from_peak_usdt"), 5.0),
        "pnl_giveback_min_peak_usdt": _num(params.get("pnl_giveback_min_peak_usdt"), 0.0),
        "sl_trigger_mode": str(params.get("sl_trigger_mode", "live_price")).lower()
        if str(params.get("sl_trigger_mode", "live_price")).lower() in ("live_price", "candle_close")
        else "live_price",
        "entry_mode": str(params.get("entry_mode", "cross_only"))
        if str(params.get("entry_mode", "cross_only"))
        in ("cross_only", "cross_or_trend", "ema_alignment")
        else "cross_only",
        "trend_entry_max_candles_after_cross": _num(params.get("trend_entry_max_candles_after_cross"), 0, int),
        "trend_entry_unlimited_after_cross": _bool_param(params.get("trend_entry_unlimited_after_cross"), False),
        "trend_entry_max_per_regime": _num(params.get("trend_entry_max_per_regime"), 1, int),
        "trend_entry_require_ema_separation": _bool_param(params.get("trend_entry_require_ema_separation"), True),
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









