package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Request DTO for starting a walk-forward analysis
 */
data class WalkForwardRequestDto(
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("strategy_type")
    val strategyType: String, // "scalping", "reverse_scalping", "range_mean_reversion"
    @SerializedName("name")
    val name: String? = null,
    @SerializedName("start_time")
    val startTime: String, // ISO 8601 datetime string
    @SerializedName("end_time")
    val endTime: String, // ISO 8601 datetime string
    @SerializedName("training_period_days")
    val trainingPeriodDays: Int = 30,
    @SerializedName("test_period_days")
    val testPeriodDays: Int = 7,
    @SerializedName("step_size_days")
    val stepSizeDays: Int = 7,
    @SerializedName("window_type")
    val windowType: String = "rolling", // "rolling" or "expanding"
    @SerializedName("optimize_params")
    val optimizeParams: Map<String, List<Any>>? = null,
    @SerializedName("leverage")
    val leverage: Int = 5,
    @SerializedName("risk_per_trade")
    val riskPerTrade: Double = 0.01,
    @SerializedName("fixed_amount")
    val fixedAmount: Double? = null,
    @SerializedName("initial_balance")
    val initialBalance: Double = 1000.0,
    @SerializedName("params")
    val params: Map<String, Any> = emptyMap(),
    @SerializedName("optimization_metric")
    val optimizationMetric: String = "robust_score", // "sharpe_ratio", "robust_score", "total_return", "win_rate", "profit_factor"
    @SerializedName("optimization_method")
    val optimizationMethod: String = "grid_search", // "grid_search" or "random_search"
    @SerializedName("min_trades_guardrail")
    val minTradesGuardrail: Int = 5,
    @SerializedName("max_drawdown_cap")
    val maxDrawdownCap: Double = 50.0,
    @SerializedName("lottery_trade_threshold")
    val lotteryTradeThreshold: Double = 0.5
)



