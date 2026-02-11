package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class ErrorResponse(
    @SerializedName("error")
    val error: String? = null,
    @SerializedName("message")
    val message: String,
    @SerializedName("details")
    val details: Map<String, Any>? = null
)












































