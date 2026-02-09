package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * DTO for Strategy Statistics
 */
data class StrategyStatsDto(
    @SerializedName("total_trades")
    val totalTrades: Int = 0,
    @SerializedName("completed_trades")
    val completedTrades: Int = 0,
    @SerializedName("winning_trades")
    val winningTrades: Int = 0,
    @SerializedName("losing_trades")
    val losingTrades: Int = 0,
    @SerializedName("total_pnl")
    val totalPnl: Double = 0.0,
    @SerializedName("realized_pnl")
    val realizedPnl: Double = 0.0,
    @SerializedName("unrealized_pnl")
    val unrealizedPnl: Double = 0.0,
    @SerializedName("win_rate")
    val winRate: Double = 0.0,
    @SerializedName("avg_profit_per_trade")
    val avgProfitPerTrade: Double = 0.0,
    @SerializedName("largest_win")
    val largestWin: Double? = null,
    @SerializedName("largest_loss")
    val largestLoss: Double? = null,
    @SerializedName("last_trade_at")
    val lastTradeAt: String? = null
)


