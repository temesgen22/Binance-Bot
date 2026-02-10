package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Progress DTO for walk-forward analysis
 */
data class WalkForwardProgressDto(
    @SerializedName("task_id")
    val taskId: String,
    @SerializedName("status")
    val status: String, // "running", "completed", "failed"
    @SerializedName("current_window")
    val currentWindow: Int,
    @SerializedName("total_windows")
    val totalWindows: Int,
    @SerializedName("progress_pct")
    val progressPct: Double,
    @SerializedName("estimated_time_remaining_seconds")
    val estimatedTimeRemainingSeconds: Int? = null,
    @SerializedName("current_phase")
    val currentPhase: String? = null, // "training", "testing", "optimizing"
    @SerializedName("message")
    val message: String? = null
)



