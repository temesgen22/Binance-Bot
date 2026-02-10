package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Auto-Tuning Configuration DTO
 */
data class AutoTuningConfigDto(
    @SerializedName("evaluation_period_days")
    val evaluationPeriodDays: Int = 7,
    @SerializedName("min_trades_for_evaluation")
    val minTradesForEvaluation: Int = 10,
    @SerializedName("performance_threshold_pct")
    val performanceThresholdPct: Double = -5.0,
    @SerializedName("optimization_metric")
    val optimizationMetric: String = "sharpe_ratio", // "sharpe_ratio", "total_return", "win_rate"
    @SerializedName("param_ranges")
    val paramRanges: Map<String, List<Any>> = emptyMap()
)



