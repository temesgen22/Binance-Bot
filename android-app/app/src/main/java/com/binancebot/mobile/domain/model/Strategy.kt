package com.binancebot.mobile.domain.model

/**
 * Domain model for Strategy.
 * This is the business logic model, separate from data layer.
 */
data class Strategy(
    val id: String,
    val name: String,
    val symbol: String,
    val strategyType: String,
    val status: String,
    val leverage: Int,
    val riskPerTrade: Double? = null,
    val fixedAmount: Double? = null,
    val accountId: String,
    val positionSide: String? = null,
    val positionSize: Double? = null,
    val entryPrice: Double? = null,
    val currentPrice: Double? = null,
    val unrealizedPnL: Double? = null,
    val realizedPnL: Double? = null,
    val totalTrades: Int? = null,
    val autoTuningEnabled: Boolean = false,
    val lastSignal: String? = null
) {
    val isRunning: Boolean
        get() = status == "running"
    
    val isStopped: Boolean
        get() = status == "stopped"
    
    val hasPosition: Boolean
        get() = positionSize != null && positionSize > 0
}































