package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class OverallStatsDto(
    @SerializedName("total_strategies") val totalStrategies: Int,
    @SerializedName("running_strategies") val runningStrategies: Int
)
