package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class MarketAnalysisResponse(
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("interval")
    val interval: String,
    @SerializedName("current_price")
    val currentPrice: Double,
    @SerializedName("market_condition")
    val marketCondition: String, // "TRENDING", "SIDEWAYS", "UNCERTAIN", "UNKNOWN"
    @SerializedName("confidence")
    val confidence: Double, // 0.0 to 0.95
    @SerializedName("recommendation")
    val recommendation: String,
    @SerializedName("indicators")
    val indicators: Map<String, Any>,
    @SerializedName("range_info")
    val rangeInfo: Map<String, Any>? = null,
    @SerializedName("trend_info")
    val trendInfo: Map<String, Any>,
    @SerializedName("volume_analysis")
    val volumeAnalysis: Map<String, Any>? = null
)

























