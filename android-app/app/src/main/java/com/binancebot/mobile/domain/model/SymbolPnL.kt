package com.binancebot.mobile.domain.model

data class SymbolPnL(
    val symbol: String,
    val totalRealizedPnL: Double = 0.0,
    val totalUnrealizedPnL: Double = 0.0,
    val totalPnL: Double = 0.0,
    val openPositions: List<Position> = emptyList(),
    val totalTrades: Int = 0,
    val completedTrades: Int = 0,
    val winRate: Double = 0.0,
    val winningTrades: Int = 0,
    val losingTrades: Int = 0,
    val totalTradeFees: Double? = null,
    val totalFundingFees: Double? = null
)

