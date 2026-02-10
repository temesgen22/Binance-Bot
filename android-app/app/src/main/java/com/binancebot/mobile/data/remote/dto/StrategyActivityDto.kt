package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Strategy Activity Event DTO
 */
data class StrategyActivityDto(
    @SerializedName("event_type")
    val eventType: String,
    @SerializedName("event_level")
    val eventLevel: String,
    @SerializedName("message")
    val message: String,
    @SerializedName("created_at")
    val createdAt: String,
    @SerializedName("metadata")
    val metadata: Map<String, Any>? = null
)



