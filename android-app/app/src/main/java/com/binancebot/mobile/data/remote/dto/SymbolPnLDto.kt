package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class SymbolPnLDto(
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("total_realized_pnl")
    val totalRealizedPnL: Double = 0.0,
    @SerializedName("total_unrealized_pnl")
    val totalUnrealizedPnL: Double = 0.0,
    @SerializedName("total_pnl")
    val totalPnL: Double = 0.0,
    @SerializedName("open_positions")
    val openPositions: List<PositionSummaryDto> = emptyList(),
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
    @SerializedName("total_trade_fees")
    val totalTradeFees: Double? = null,
    @SerializedName("total_funding_fees")
    val totalFundingFees: Double? = null
)

