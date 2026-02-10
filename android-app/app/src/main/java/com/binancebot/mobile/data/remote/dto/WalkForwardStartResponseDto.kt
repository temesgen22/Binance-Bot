package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Response DTO for starting walk-forward analysis
 */
data class WalkForwardStartResponseDto(
    @SerializedName("task_id")
    val taskId: String,
    @SerializedName("message")
    val message: String,
    @SerializedName("total_windows")
    val totalWindows: Int
)



