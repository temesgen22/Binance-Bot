package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class PriceAlertDto(
    @SerializedName("id") val id: String,
    @SerializedName("user_id") val userId: String,
    @SerializedName("symbol") val symbol: String,
    @SerializedName("alert_type") val alertType: String,
    @SerializedName("target_price") val targetPrice: Double,
    @SerializedName("enabled") val enabled: Boolean,
    @SerializedName("last_price") val lastPrice: Double? = null,
    @SerializedName("trigger_once") val triggerOnce: Boolean,
    @SerializedName("triggered_at") val triggeredAt: String? = null,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String
)

data class PriceAlertListResponse(
    @SerializedName("alerts") val alerts: List<PriceAlertDto>,
    @SerializedName("count") val count: Int
)

data class CreatePriceAlertRequest(
    @SerializedName("symbol") val symbol: String,
    @SerializedName("alert_type") val alertType: String,
    @SerializedName("target_price") val targetPrice: Double,
    @SerializedName("trigger_once") val triggerOnce: Boolean = true
)

data class UpdatePriceAlertRequest(
    @SerializedName("symbol") val symbol: String? = null,
    @SerializedName("alert_type") val alertType: String? = null,
    @SerializedName("target_price") val targetPrice: Double? = null,
    @SerializedName("enabled") val enabled: Boolean? = null,
    @SerializedName("trigger_once") val triggerOnce: Boolean? = null
)
