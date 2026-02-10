package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Backtest Result DTO matching the backend BacktestResult model
 */
data class BacktestResultDto(
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("strategy_type")
    val strategyType: String,
    @SerializedName("start_time")
    val startTime: String, // ISO 8601 datetime string
    @SerializedName("end_time")
    val endTime: String, // ISO 8601 datetime string
    @SerializedName("initial_balance")
    val initialBalance: Double,
    @SerializedName("final_balance")
    val finalBalance: Double,
    @SerializedName("total_pnl")
    val totalPnL: Double,
    @SerializedName("total_return_pct")
    val totalReturnPct: Double,
    @SerializedName("total_trades")
    val totalTrades: Int,
    @SerializedName("completed_trades")
    val completedTrades: Int,
    @SerializedName("open_trades")
    val openTrades: Int,
    @SerializedName("winning_trades")
    val winningTrades: Int,
    @SerializedName("losing_trades")
    val losingTrades: Int,
    @SerializedName("win_rate")
    val winRate: Double,
    @SerializedName("total_fees")
    val totalFees: Double,
    @SerializedName("avg_profit_per_trade")
    val avgProfitPerTrade: Double,
    @SerializedName("largest_win")
    val largestWin: Double,
    @SerializedName("largest_loss")
    val largestLoss: Double,
    @SerializedName("max_drawdown")
    val maxDrawdown: Double,
    @SerializedName("max_drawdown_pct")
    val maxDrawdownPct: Double,
    @SerializedName("trades")
    val trades: List<Map<String, Any>>? = null,
    @SerializedName("klines")
    val klines: List<List<Any>>? = null,
    @SerializedName("indicators")
    val indicators: Map<String, Any>? = null
) {
    // Helper properties for compatibility with existing code
    val id: String get() = "${symbol}_${strategyType}_${startTime}"
    val strategyId: String? get() = null
    val strategyName: String? get() = strategyType.replace("_", " ").replaceFirstChar { it.uppercase() }
    val startDate: String get() = startTime.split("T")[0] // Extract date part
    val endDate: String get() = endTime.split("T")[0] // Extract date part
    val profitFactor: Double? get() = null // Not in backend response
    val sharpeRatio: Double? get() = null // Not in backend response
    val status: String get() = "completed"
    val createdAt: String? get() = null
}



