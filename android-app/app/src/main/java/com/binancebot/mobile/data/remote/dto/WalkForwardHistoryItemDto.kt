package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Walk-Forward History Item DTO
 */
data class WalkForwardHistoryItemDto(
    @SerializedName("id")
    val id: String,
    @SerializedName("task_id")
    val taskId: String? = null,
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("strategy_type")
    val strategyType: String,
    @SerializedName("name")
    val name: String? = null,
    @SerializedName("start_time")
    val startTime: String,
    @SerializedName("end_time")
    val endTime: String,
    @SerializedName("status")
    val status: String, // "running", "completed", "failed"
    @SerializedName("total_windows")
    val totalWindows: Int,
    @SerializedName("completed_windows")
    val completedWindows: Int? = null,
    @SerializedName("total_return_pct")
    val totalReturnPct: Double? = null,
    @SerializedName("created_at")
    val createdAt: String? = null,
    @SerializedName("completed_at")
    val completedAt: String? = null
)



