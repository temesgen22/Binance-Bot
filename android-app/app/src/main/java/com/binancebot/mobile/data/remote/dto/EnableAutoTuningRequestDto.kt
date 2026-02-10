package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Request DTO for enabling auto-tuning
 */
data class EnableAutoTuningRequestDto(
    @SerializedName("config")
    val config: AutoTuningConfigDto
)



