package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class CreateAccountRequest(
    @SerializedName("account_id") val accountId: String,
    @SerializedName("name") val name: String? = null,
    @SerializedName("api_key") val apiKey: String? = null,
    @SerializedName("api_secret") val apiSecret: String? = null,
    @SerializedName("exchange_platform") val exchangePlatform: String = "binance",
    @SerializedName("testnet") val testnet: Boolean = true,
    @SerializedName("is_default") val isDefault: Boolean = false,
    @SerializedName("paper_trading") val paperTrading: Boolean = false,
    @SerializedName("paper_balance") val paperBalance: Double? = null
)
