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
    val id: String,
    @SerializedName("timestamp")
    val timestamp: String,
    @SerializedName("level")
    val level: String,
    @SerializedName("message")
    val message: String,
    @SerializedName("symbol")
    val symbol: String? = null
)
































