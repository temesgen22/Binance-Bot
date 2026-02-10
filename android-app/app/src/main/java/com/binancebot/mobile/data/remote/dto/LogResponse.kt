package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class LogResponse(
    @SerializedName("entries")
    val entries: List<LogEntryDto>,
    @SerializedName("total")
    val total: Int
)

data class LogEntryDto(
    @SerializedName("id")
    val id: String? = null,
    @SerializedName("timestamp")
    val timestamp: String? = null,
    @SerializedName("level")
    val level: String? = null,
    @SerializedName("message")
    val message: String? = null,
    @SerializedName("symbol")
    val symbol: String? = null
)



































