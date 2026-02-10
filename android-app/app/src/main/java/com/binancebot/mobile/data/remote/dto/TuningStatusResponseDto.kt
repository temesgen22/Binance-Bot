package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Auto-Tuning Status Response DTO
 */
data class TuningStatusResponseDto(
    @SerializedName("strategy_id")
    val strategyId: String,
    @SerializedName("enabled")
    val enabled: Boolean,
    @SerializedName("config")
    val config: AutoTuningConfigDto? = null,
    @SerializedName("last_tuning_time")
    val lastTuningTime: String? = null,
    @SerializedName("last_tuning_result")
    val lastTuningResult: Map<String, Any>? = null
)



