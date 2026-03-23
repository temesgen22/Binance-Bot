package com.binancebot.mobile.presentation.util

/**
 * Strategy types supported by backtesting and walk-forward APIs, with display names,
 * default parameters, and parameter definitions for dynamic UI (aligned with web app backtesting.html strategyParams).
 */
object BacktestStrategyDefaults {

    /** (strategy_type_value, display_name) for dropdowns */
    val STRATEGY_TYPES: List<Pair<String, String>> = listOf(
        "scalping" to "EMA Scalping",
        "reverse_scalping" to "Reverse Scalping (Contrarian)",
        "range_mean_reversion" to "Range Mean Reversion"
    )

    /** Kline interval options (same as web app) */
    val KLINE_INTERVAL_OPTIONS: List<String> = listOf(
        "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"
    )

    /** Parameter definition for dynamic form (like web app strategyParams) */
    sealed class ParamDef(open val key: String, open val label: String) {
        data class Number(
            override val key: String,
            override val label: String,
            val value: Double,
            val min: Double,
            val max: Double,
            val step: Double = 0.001
        ) : ParamDef(key, label)

        data class Int(
            override val key: String,
            override val label: String,
            val value: kotlin.Int,
            val min: kotlin.Int,
            val max: kotlin.Int
        ) : ParamDef(key, label)

        data class Checkbox(
            override val key: String,
            override val label: String,
            val value: Boolean
        ) : ParamDef(key, label)

        data class Select(
            override val key: String,
            override val label: String,
            val value: String,
            val options: List<String>
        ) : ParamDef(key, label)
    }

    /**
     * Parameter definitions for the strategy type so the UI can show labeled inputs
     * (same structure as web app strategyParams).
     */
    fun getParameterDefinitions(strategyType: String): List<ParamDef> = when (strategyType) {
        "scalping", "reverse_scalping" -> listOf(
            ParamDef.Select("kline_interval", "Kline Interval", "1m", KLINE_INTERVAL_OPTIONS),
            ParamDef.Int("ema_fast", "Fast EMA Period", 8, 1, 200),
            ParamDef.Int("ema_slow", "Slow EMA Period", 21, 2, 400),
            ParamDef.Number("take_profit_pct", "Take Profit %", 0.004, 0.001, 0.1, 0.001),
            ParamDef.Number("stop_loss_pct", "Stop Loss %", 0.002, 0.001, 0.1, 0.001),
            ParamDef.Checkbox("enable_short", "Enable Short Trading", true),
            ParamDef.Number("min_ema_separation", "Min EMA Separation", 0.0002, 0.0, 0.01, 0.0001),
            ParamDef.Checkbox("enable_htf_bias", "Enable HTF Bias", true),
            ParamDef.Int("cooldown_candles", "Cooldown Candles", 2, 0, 10),
            ParamDef.Checkbox("enable_ema_cross_exit", "Enable EMA Cross Exits", true),
            ParamDef.Checkbox("use_rsi_filter", "Use RSI Filter", false),
            ParamDef.Int("rsi_period", "RSI Period", 14, 1, 200),
            ParamDef.Number("rsi_long_min", "RSI Long Min", 50.0, 0.0, 100.0, 0.1),
            ParamDef.Number("rsi_short_max", "RSI Short Max", 50.0, 0.0, 100.0, 0.1),
            ParamDef.Checkbox("use_atr_filter", "Use ATR Filter", false),
            ParamDef.Int("atr_period", "ATR Period", 14, 1, 200),
            ParamDef.Number("atr_min_pct", "ATR Min %", 0.0, 0.0, 1000.0, 0.1),
            ParamDef.Number("atr_max_pct", "ATR Max %", 100.0, 0.0, 1000.0, 0.1),
            ParamDef.Checkbox("use_volume_filter", "Use Volume Filter", false),
            ParamDef.Int("volume_ma_period", "Volume MA Period", 20, 1, 500),
            ParamDef.Number("volume_multiplier_min", "Volume Multiplier Min", 1.0, 0.0, 1000.0, 0.1),
            ParamDef.Checkbox("use_structure_filter", "Use Market Structure Filter (HH/HL vs LH/LL)", false),
            ParamDef.Int("structure_left_bars", "Structure Pivot Left Bars", 2, 1, 20),
            ParamDef.Int("structure_right_bars", "Structure Pivot Right Bars", 2, 1, 20),
            ParamDef.Checkbox("structure_confirm_on_close", "Structure Confirm on Candle Close", true),
            ParamDef.Checkbox("trailing_stop_enabled", "Trailing Stop", false),
            ParamDef.Number("trailing_stop_activation_pct", "Trailing Activation %", 0.0, 0.0, 0.1, 0.001),
            ParamDef.Select("sl_trigger_mode", "SL Trigger", "live_price", listOf("live_price", "candle_close"))
        )
        "range_mean_reversion" -> listOf(
            ParamDef.Select("kline_interval", "Kline Interval", "5m", KLINE_INTERVAL_OPTIONS),
            ParamDef.Int("lookback_period", "Lookback Period", 150, 50, 500),
            ParamDef.Number("buy_zone_pct", "Buy Zone %", 0.2, 0.01, 0.5, 0.01),
            ParamDef.Number("sell_zone_pct", "Sell Zone %", 0.2, 0.01, 0.5, 0.01),
            ParamDef.Int("ema_fast_period", "Fast EMA Period", 20, 5, 100),
            ParamDef.Int("ema_slow_period", "Slow EMA Period", 50, 10, 200),
            ParamDef.Number("max_ema_spread_pct", "Max EMA Spread %", 0.005, 0.0, 0.02, 0.001),
            ParamDef.Number("max_atr_multiplier", "Max ATR Multiplier", 2.0, 0.1, 100.0, 0.1),
            ParamDef.Int("rsi_period", "RSI Period", 14, 5, 50),
            ParamDef.Int("rsi_oversold", "RSI Oversold", 40, 0, 50),
            ParamDef.Int("rsi_overbought", "RSI Overbought", 60, 50, 100),
            ParamDef.Number("tp_buffer_pct", "TP Buffer %", 0.001, 0.0, 0.05, 0.0001),
            ParamDef.Number("sl_buffer_pct", "SL Buffer %", 0.002, 0.0, 0.05, 0.0001),
            ParamDef.Int("cooldown_candles", "Cooldown Candles", 2, 0, 10),
            ParamDef.Int("max_range_invalid_candles", "Max Range Invalid Candles", 20, 5, 100),
            ParamDef.Checkbox("enable_short", "Enable Short Trading", true),
            ParamDef.Select("sl_trigger_mode", "SL Trigger", "live_price", listOf("live_price", "candle_close"))
        )
        else -> emptyList()
    }

    /**
     * Default strategy parameters per type (matches web app defaults).
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
            "use_rsi_filter" to false,
            "rsi_period" to 14,
            "rsi_long_min" to 50.0,
            "rsi_short_max" to 50.0,
            "use_atr_filter" to false,
            "atr_period" to 14,
            "atr_min_pct" to 0.0,
            "atr_max_pct" to 100.0,
            "use_volume_filter" to false,
            "volume_ma_period" to 20,
            "volume_multiplier_min" to 1.0,
            "use_structure_filter" to false,
            "structure_left_bars" to 2,
            "structure_right_bars" to 2,
            "structure_confirm_on_close" to true,
            "trailing_stop_enabled" to false,
            "trailing_stop_activation_pct" to 0.0,
            "sl_trigger_mode" to "live_price"
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
            "enable_short" to true,
            "sl_trigger_mode" to "live_price"
        )
        else -> emptyMap()
    }
}
