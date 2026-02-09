package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class BacktestResultDto(
    @SerializedName("id")
    val id: String,
    @SerializedName("strategy_id")
    val strategyId: String? = null,
    @SerializedName("strategy_name")
    val strategyName: String? = null,
    @SerializedName("start_date")
    val startDate: String,
    @SerializedName("end_date")
    val endDate: String,
    @SerializedName("total_pnl")
    val totalPnL: Double = 0.0,
    @SerializedName("total_trades")
    val totalTrades: Int = 0,
    @SerializedName("win_rate")
    val winRate: Double = 0.0,
    @SerializedName("profit_factor")
    val profitFactor: Double? = null,
    @SerializedName("max_drawdown")
    val maxDrawdown: Double? = null,
    @SerializedName("sharpe_ratio")
    val sharpeRatio: Double? = null,
    @SerializedName("status")
    val status: String = "completed",
    @SerializedName("created_at")
    val createdAt: String? = null
)



