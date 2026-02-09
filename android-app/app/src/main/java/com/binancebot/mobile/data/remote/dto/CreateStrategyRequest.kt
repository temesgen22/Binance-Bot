package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class CreateStrategyRequest(
    @SerializedName("name")
    val name: String,
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("strategy_type")
    val strategyType: String,
    @SerializedName("leverage")
    val leverage: Int,
    @SerializedName("risk_per_trade")
    val riskPerTrade: Double? = null,
    @SerializedName("fixed_amount")
    val fixedAmount: Double? = null,
    @SerializedName("params")
    val params: Map<String, Any>? = null,
    @SerializedName("account_id")
    val accountId: String
)




























