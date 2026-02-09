package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class DashboardOverviewDto(
    @SerializedName("total_pnl")
    val totalPnL: Double,
    @SerializedName("realized_pnl")
    val realizedPnL: Double,
    @SerializedName("unrealized_pnl")
    val unrealizedPnL: Double,
    @SerializedName("pnl_change_24h")
    val pnlChange24h: Double? = null,
    @SerializedName("pnl_change_7d")
    val pnlChange7d: Double? = null,
    @SerializedName("pnl_change_30d")
    val pnlChange30d: Double? = null,
    @SerializedName("active_strategies")
    val activeStrategies: Int,
    @SerializedName("total_strategies")
    val totalStrategies: Int,
    @SerializedName("total_trades")
    val totalTrades: Int,
    @SerializedName("completed_trades")
    val completedTrades: Int,
    @SerializedName("overall_win_rate")
    val overallWinRate: Double,
    @SerializedName("best_strategy")
    val bestStrategy: StrategyPerformanceDto? = null,
    @SerializedName("worst_strategy")
    val worstStrategy: StrategyPerformanceDto? = null,
    @SerializedName("top_symbol")
    val topSymbol: SymbolPnLDto? = null,
    @SerializedName("account_balance")
    val accountBalance: Double? = null,
    @SerializedName("total_trade_fees")
    val totalTradeFees: Double? = null,
    @SerializedName("total_funding_fees")
    val totalFundingFees: Double? = null,
    @SerializedName("pnl_timeline")
    val pnlTimeline: List<Map<String, Any>>? = null
)

data class SymbolPnLDto(
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("total_realized_pnl")
    val totalRealizedPnL: Double,
    @SerializedName("total_unrealized_pnl")
    val totalUnrealizedPnL: Double,
    @SerializedName("total_pnl")
    val totalPnL: Double
)
