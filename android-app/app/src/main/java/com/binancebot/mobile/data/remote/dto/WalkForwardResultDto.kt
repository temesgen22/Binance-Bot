package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Walk-Forward Result DTO
 */
data class WalkForwardResultDto(
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("strategy_type")
    val strategyType: String,
    @SerializedName("overall_start_time")
    val overallStartTime: String,
    @SerializedName("overall_end_time")
    val overallEndTime: String,
    @SerializedName("training_period_days")
    val trainingPeriodDays: Int,
    @SerializedName("test_period_days")
    val testPeriodDays: Int,
    @SerializedName("step_size_days")
    val stepSizeDays: Int,
    @SerializedName("window_type")
    val windowType: String,
    @SerializedName("total_windows")
    val totalWindows: Int,
    @SerializedName("windows")
    val windows: List<Map<String, Any>>? = null,
    @SerializedName("total_return_pct")
    val totalReturnPct: Double,
    @SerializedName("avg_window_return_pct")
    val avgWindowReturnPct: Double,
    @SerializedName("consistency_score")
    val consistencyScore: Double,
    @SerializedName("sharpe_ratio")
    val sharpeRatio: Double,
    @SerializedName("max_drawdown_pct")
    val maxDrawdownPct: Double,
    @SerializedName("total_trades")
    val totalTrades: Int,
    @SerializedName("avg_win_rate")
    val avgWinRate: Double,
    @SerializedName("equity_curve")
    val equityCurve: List<Map<String, Any>>? = null
)



