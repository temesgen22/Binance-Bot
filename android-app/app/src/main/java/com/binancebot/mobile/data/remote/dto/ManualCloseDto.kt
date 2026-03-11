package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/** Request body for manual close of a strategy-owned position. */
data class ManualCloseRequestDto(
    @SerializedName("symbol")
    val symbol: String? = null,
    @SerializedName("position_side")
    val positionSide: String? = null
)

/** Response from manual close endpoint. */
data class ManualCloseResponseDto(
    @SerializedName("strategy_id")
    val strategyId: String,
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("position_side")
    val positionSide: String,
    @SerializedName("closed_quantity")
    val closedQuantity: Double,
    @SerializedName("order_id")
    val orderId: Long,
    @SerializedName("exit_reason")
    val exitReason: String
)
