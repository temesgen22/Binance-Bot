package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Request DTO for running a backtest
 */
data class BacktestRequestDto(
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("strategy_type")
    val strategyType: String, // "scalping", "reverse_scalping", "range_mean_reversion"
    @SerializedName("start_time")
    val startTime: String, // ISO 8601 datetime string
    @SerializedName("end_time")
    val endTime: String, // ISO 8601 datetime string
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
    @SerializedName("include_klines")
    val includeKlines: Boolean = true
)



