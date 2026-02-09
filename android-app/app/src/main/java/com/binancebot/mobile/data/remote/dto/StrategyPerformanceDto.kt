package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class StrategyPerformanceDto(
    @SerializedName("strategy_id")
    val strategyId: String,
    @SerializedName("strategy_name")
    val strategyName: String,
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("strategy_type")
    val strategyType: String,
    @SerializedName("status")
    val status: String,
    @SerializedName("total_realized_pnl")
    val totalRealizedPnl: Double = 0.0,
    @SerializedName("total_unrealized_pnl")
    val totalUnrealizedPnl: Double = 0.0,
    @SerializedName("total_pnl")
    val totalPnl: Double = 0.0,
    @SerializedName("total_trades")
    val totalTrades: Int = 0,
    @SerializedName("completed_trades")
    val completedTrades: Int = 0,
    @SerializedName("win_rate")
    val winRate: Double = 0.0,
    @SerializedName("winning_trades")
    val winningTrades: Int = 0,
    @SerializedName("losing_trades")
    val losingTrades: Int = 0,
    @SerializedName("avg_profit_per_trade")
    val avgProfitPerTrade: Double = 0.0,
    @SerializedName("largest_win")
    val largestWin: Double = 0.0,
    @SerializedName("largest_loss")
    val largestLoss: Double = 0.0,
    @SerializedName("position_size")
    val positionSize: Double? = null,
    @SerializedName("position_side")
    val positionSide: String? = null,
    @SerializedName("entry_price")
    val entryPrice: Double? = null,
    @SerializedName("current_price")
    val currentPrice: Double? = null,
    @SerializedName("leverage")
    val leverage: Int,
    @SerializedName("risk_per_trade")
    val riskPerTrade: Double,
    @SerializedName("fixed_amount")
    val fixedAmount: Double? = null,
    @SerializedName("params")
    val params: Map<String, Any> = emptyMap(),
    @SerializedName("created_at")
    val createdAt: String,
    @SerializedName("started_at")
    val startedAt: String? = null,
    @SerializedName("stopped_at")
    val stoppedAt: String? = null,
    @SerializedName("last_trade_at")
    val lastTradeAt: String? = null,
    @SerializedName("last_signal")
    val lastSignal: String? = null,
    @SerializedName("account_id")
    val accountId: String? = null,
    @SerializedName("account_info")
    val accountInfo: Map<String, Any>? = null,
    @SerializedName("rank")
    val rank: Int? = null,
    @SerializedName("percentile")
    val percentile: Double? = null,
    @SerializedName("auto_tuning_enabled")
    val autoTuningEnabled: Boolean = false,
    @SerializedName("total_funding_fees")
    val totalFundingFees: Double? = null
)

data class StrategyPerformanceListDto(
    @SerializedName("strategies")
    val strategies: List<StrategyPerformanceDto> = emptyList(),
    @SerializedName("total_strategies")
    val totalStrategies: Int = 0,
    @SerializedName("ranked_by")
    val rankedBy: String = "total_pnl",
    @SerializedName("summary")
    val summary: Map<String, Any> = emptyMap()
)



























