package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Auto-Tuning History Item DTO
 */
data class TuningHistoryItemDto(
    @SerializedName("id")
    val id: String,
    @SerializedName("strategy_id")
    val strategyId: String,
    @SerializedName("tuning_time")
    val tuningTime: String,
    @SerializedName("old_params")
    val oldParams: Map<String, Any>? = null,
    @SerializedName("new_params")
    val newParams: Map<String, Any>? = null,
    @SerializedName("performance_before")
    val performanceBefore: Map<String, Any>? = null,
    @SerializedName("performance_after")
    val performanceAfter: Map<String, Any>? = null,
    @SerializedName("improvement_pct")
    val improvementPct: Double? = null,
    @SerializedName("status")
    val status: String // "success", "failed", "no_improvement"
)



