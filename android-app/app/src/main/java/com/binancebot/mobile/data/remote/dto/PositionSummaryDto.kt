package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class PositionSummaryDto(
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("position_size")
    val positionSize: Double,
    @SerializedName("entry_price")
    val entryPrice: Double,
    @SerializedName("current_price")
    val currentPrice: Double,
    @SerializedName("position_side")
    val positionSide: String, // "LONG" or "SHORT"
    @SerializedName("unrealized_pnl")
    val unrealizedPnL: Double,
    @SerializedName("leverage")
    val leverage: Int,
    @SerializedName("strategy_id")
    val strategyId: String? = null,
    @SerializedName("strategy_name")
    val strategyName: String? = null
)

