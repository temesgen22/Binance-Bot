package com.binancebot.mobile.domain.model

/**
 * Domain model for Trade.
 * This is the business logic model, separate from data layer.
 */
data class Trade(
    val id: String,
    val strategyId: String,
    val orderId: Long,
    val symbol: String,
    val side: String,
    val executedQty: Double,
    val avgPrice: Double,
    val commission: Double? = null,
    val timestamp: Long,
    val positionSide: String? = null,
    val exitReason: String? = null
) {
    val isBuy: Boolean
        get() = side.uppercase() == "BUY"
    
    val isSell: Boolean
        get() = side.uppercase() == "SELL"
    
    val isEntry: Boolean
        get() = exitReason == null
    
    val isExit: Boolean
        get() = exitReason != null
    
    val notional: Double
        get() = executedQty * avgPrice
}
































