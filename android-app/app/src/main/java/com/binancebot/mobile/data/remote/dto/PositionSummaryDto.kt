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
    @SerializedName("max_unrealized_pnl")
    val maxUnrealizedPnL: Double? = null,
    @SerializedName("leverage")
    val leverage: Int,
    @SerializedName("strategy_id")
    val strategyId: String? = null,
    @SerializedName("strategy_name")
    val strategyName: String? = null,
    @SerializedName("account_id")
    val accountId: String? = null,
    @SerializedName("liquidation_price")
    val liquidationPrice: Double? = null,
    @SerializedName("initial_margin")
    val initialMargin: Double? = null,
    @SerializedName("margin_type")
    val marginType: String? = null,
    @SerializedName("tp_price")
    val tpPrice: Double? = null,
    @SerializedName("sl_price")
    val slPrice: Double? = null,
    @SerializedName("tp_order_id")
    val tpOrderId: Long? = null,
    @SerializedName("sl_order_id")
    val slOrderId: Long? = null,
    @SerializedName("trailing_stop_enabled")
    val trailingStopEnabled: Boolean = false,
    @SerializedName("last_funding_rate")
    val lastFundingRate: Double? = null,
    @SerializedName("next_funding_time_ms")
    val nextFundingTimeMs: Long? = null,
    @SerializedName("funding_interval_hours")
    val fundingIntervalHours: Int? = null,
    @SerializedName("opened_at")
    val openedAt: String? = null,
)

