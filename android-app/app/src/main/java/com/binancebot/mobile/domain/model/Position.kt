package com.binancebot.mobile.domain.model

data class Position(
    val symbol: String,
    val positionSize: Double,
    val entryPrice: Double,
    val currentPrice: Double,
    val positionSide: String, // "LONG" or "SHORT"
    val unrealizedPnL: Double,
    /** Peak open unrealized PnL (USDT) from mark-price stream when available */
    val maxUnrealizedPnL: Double? = null,
    val leverage: Int,
    val strategyId: String? = null,
    val strategyName: String? = null,
    val accountId: String? = null,
    val liquidationPrice: Double? = null,
    val initialMargin: Double? = null,
    val marginType: String? = null // "CROSSED" or "ISOLATED"
) {
    val isLong: Boolean
        get() = positionSide.uppercase() == "LONG"
    
    val isShort: Boolean
        get() = positionSide.uppercase() == "SHORT"
}

