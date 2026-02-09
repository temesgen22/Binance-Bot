package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class CreateAccountRequest(
    @SerializedName("account_name") val accountName: String,
    @SerializedName("api_key") val apiKey: String,
    @SerializedName("api_secret") val apiSecret: String,
    @SerializedName("testnet") val testnet: Boolean
)
