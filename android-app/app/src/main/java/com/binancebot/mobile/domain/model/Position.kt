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
    val marginType: String? = null, // "CROSSED" or "ISOLATED"
    /** Last funding rate (decimal, e.g. 0.0001) from Binance mark / premiumIndex */
    val lastFundingRate: Double? = null,
    /** Next funding settlement (Unix ms) */
    val nextFundingTimeMs: Long? = null,
    /** Funding interval in hours from fundingInfo */
    val fundingIntervalHours: Int? = null,
    /** ISO-8601 when the position was opened (from API) */
    val openedAt: String? = null,
) {
    val isLong: Boolean
        get() = positionSide.uppercase() == "LONG"
    
    val isShort: Boolean
        get() = positionSide.uppercase() == "SHORT"
}

