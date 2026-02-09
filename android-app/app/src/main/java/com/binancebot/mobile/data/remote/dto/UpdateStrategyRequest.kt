package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class UpdateStrategyRequest(
    @SerializedName("name")
    val name: String? = null,
    @SerializedName("symbol")
    val symbol: String? = null,
    @SerializedName("leverage")
    val leverage: Int? = null,
    @SerializedName("risk_per_trade")
    val riskPerTrade: Double? = null,
    @SerializedName("fixed_amount")
    val fixedAmount: Double? = null,
    @SerializedName("params")
    val params: Map<String, Any>? = null
)
































