package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class TradeReportDto(
    @SerializedName("trade_id")
    val tradeId: String,
    @SerializedName("strategy_id")
    val strategyId: String,
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("side")
    val side: String,
    @SerializedName("entry_time")
    val entryTime: String? = null,
    @SerializedName("entry_price")
    val entryPrice: Double,
    @SerializedName("exit_time")
    val exitTime: String? = null,
    @SerializedName("exit_price")
    val exitPrice: Double? = null,
    @SerializedName("quantity")
    val quantity: Double,
    @SerializedName("leverage")
    val leverage: Int,
    @SerializedName("fee_paid")
    val feePaid: Double = 0.0,
    @SerializedName("funding_fee")
    val fundingFee: Double = 0.0,
    @SerializedName("pnl_usd")
    val pnlUsd: Double,
    @SerializedName("pnl_pct")
    val pnlPct: Double,
    @SerializedName("exit_reason")
    val exitReason: String? = null,
    @SerializedName("initial_margin")
    val initialMargin: Double? = null,
    @SerializedName("margin_type")
    val marginType: String? = null,
    @SerializedName("notional_value")
    val notionalValue: Double? = null,
    @SerializedName("entry_order_id")
    val entryOrderId: Long? = null,
    @SerializedName("exit_order_id")
    val exitOrderId: Long? = null
)

data class StrategyReportDto(
    @SerializedName("strategy_id")
    val strategyId: String,
    @SerializedName("strategy_name")
    val strategyName: String,
    @SerializedName("strategy_type")
    val strategyType: String? = null,
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("created_at")
    val createdAt: String? = null,
    @SerializedName("stopped_at")
    val stoppedAt: String? = null,
    @SerializedName("total_trades")
    val totalTrades: Int,
    @SerializedName("wins")
    val wins: Int,
    @SerializedName("losses")
    val losses: Int,
    @SerializedName("win_rate")
    val winRate: Double,
    @SerializedName("total_profit_usd")
    val totalProfitUsd: Double,
    @SerializedName("total_loss_usd")
    val totalLossUsd: Double,
    @SerializedName("net_pnl")
    val netPnl: Double,
    @SerializedName("total_fee")
    val totalFee: Double = 0.0,
    @SerializedName("total_funding_fee")
    val totalFundingFee: Double = 0.0,
    @SerializedName("trades")
    val trades: List<TradeReportDto> = emptyList()
)

data class TradingReportDto(
    @SerializedName("strategies")
    val strategies: List<StrategyReportDto> = emptyList(),
    @SerializedName("total_strategies")
    val totalStrategies: Int = 0,
    @SerializedName("total_trades")
    val totalTrades: Int = 0,
    @SerializedName("overall_win_rate")
    val overallWinRate: Double = 0.0,
    @SerializedName("overall_net_pnl")
    val overallNetPnl: Double = 0.0,
    @SerializedName("report_generated_at")
    val reportGeneratedAt: String,
    @SerializedName("filters")
    val filters: Map<String, Any>? = null
)



























