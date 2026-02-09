package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class TradeDto(
    @SerializedName("id")
    val id: String? = null,
    @SerializedName("strategy_id")
    val strategyId: String? = null,
    @SerializedName("order_id")
    val orderId: Long? = null,
    @SerializedName("symbol")
    val symbol: String? = null,
    @SerializedName("side")
    val side: String? = null,
    @SerializedName("executed_qty")
    val executedQty: Double? = null,
    @SerializedName("avg_price")
    val avgPrice: Double? = null,
    @SerializedName("commission")
    val commission: Double? = null,
    @SerializedName("timestamp")
    val timestamp: String? = null,
    @SerializedName("position_side")
    val positionSide: String? = null,
    @SerializedName("exit_reason")
    val exitReason: String? = null
)

