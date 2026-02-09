package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class TradeDto(
    @SerializedName("id")
    val id: String,
    @SerializedName("strategy_id")
    val strategyId: String,
    @SerializedName("order_id")
    val orderId: Long,
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("side")
    val side: String,
    @SerializedName("executed_qty")
    val executedQty: Double,
    @SerializedName("avg_price")
    val avgPrice: Double,
    @SerializedName("commission")
    val commission: Double? = null,
    @SerializedName("timestamp")
    val timestamp: String? = null,
    @SerializedName("position_side")
    val positionSide: String? = null,
    @SerializedName("exit_reason")
    val exitReason: String? = null
)

