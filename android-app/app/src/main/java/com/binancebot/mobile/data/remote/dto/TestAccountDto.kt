package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class TestAccountRequestDto(
    @SerializedName("api_key")
    val apiKey: String,
    @SerializedName("api_secret")
    val apiSecret: String,
    @SerializedName("testnet")
    val testnet: Boolean = true,
    @SerializedName("account_name")
    val accountName: String? = null
)

data class TestAccountResponseDto(
    @SerializedName("success")
    val success: Boolean,
    @SerializedName("account_name")
    val accountName: String? = null,
    @SerializedName("testnet")
    val testnet: Boolean,
    @SerializedName("connection_status")
    val connectionStatus: String,
    @SerializedName("authentication_status")
    val authenticationStatus: String,
    @SerializedName("account_info")
    val accountInfo: Map<String, Any>? = null,
    @SerializedName("balance")
    val balance: Double? = null,
    @SerializedName("permissions")
    val permissions: List<String>? = null,
    @SerializedName("error")
    val error: String? = null,
    @SerializedName("details")
    val details: Map<String, Any>? = null
)



























