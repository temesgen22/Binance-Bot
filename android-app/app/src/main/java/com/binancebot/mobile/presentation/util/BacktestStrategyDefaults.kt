package com.binancebot.mobile.presentation.util

/**
 * Strategy types supported by backtesting and walk-forward APIs, with display names
 * and default parameters (aligned with web app backtesting.html strategyParams).
 */
object BacktestStrategyDefaults {

    /** (strategy_type_value, display_name) for dropdowns */
    val STRATEGY_TYPES: List<Pair<String, String>> = listOf(
        "scalping" to "EMA Scalping",
        "reverse_scalping" to "Reverse Scalping (Contrarian)",
        "range_mean_reversion" to "Range Mean Reversion"
    )

    /**
     * Default strategy parameters per type so backtest/walk-forward run without requiring
     * the user to configure every param (matches web app defaults).
     */
    fun getDefaultParams(strategyType: String): Map<String, Any> = when (strategyType) {
        "scalping", "reverse_scalping" -> mapOf(
            "kline_interval" to "1m",
            "ema_fast" to 8,
            "ema_slow" to 21,
            "take_profit_pct" to 0.004,
            "stop_loss_pct" to 0.002,
            "enable_short" to true,
            "min_ema_separation" to 0.0002,
            "enable_htf_bias" to true,
            "cooldown_candles" to 2,
            "enable_ema_cross_exit" to true,
            "trailing_stop_enabled" to false,
            "trailing_stop_activation_pct" to 0.0
        )
        "range_mean_reversion" -> mapOf(
            "kline_interval" to "5m",
            "lookback_period" to 150,
            "buy_zone_pct" to 0.2,
            "sell_zone_pct" to 0.2,
            "ema_fast_period" to 20,
            "ema_slow_period" to 50,
            "max_ema_spread_pct" to 0.005,
            "max_atr_multiplier" to 2.0,
            "rsi_period" to 14,
            "rsi_oversold" to 40,
            "rsi_overbought" to 60,
            "tp_buffer_pct" to 0.001,
            "sl_buffer_pct" to 0.002,
            "cooldown_candles" to 2,
            "max_range_invalid_candles" to 20,
            "enable_short" to true
        )
        else -> emptyMap()
    }
}
