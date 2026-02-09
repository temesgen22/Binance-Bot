package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class StrategyComparisonResponseDto(
    @SerializedName("strategies") val strategies: List<StrategyDto>,
    @SerializedName("comparison_data") val comparisonData: Map<String, Any>
)
