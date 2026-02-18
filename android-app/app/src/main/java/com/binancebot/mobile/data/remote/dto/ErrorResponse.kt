package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * API error body. Backend uses "message" (custom handlers) or "detail" (FastAPI HTTPException).
 * Both nullable so either shape parses without failing.
 */
data class ErrorResponse(
    @SerializedName("error")
    val error: String? = null,
    @SerializedName("message")
    val message: String? = null,
    @SerializedName("detail")
    val detail: String? = null,
    @SerializedName("details")
    val details: Map<String, Any>? = null
) {
    /** User-facing text: prefer message, then detail (FastAPI), then null. */
    fun userMessage(): String? = message?.takeIf { it.isNotBlank() } ?: detail?.takeIf { it.isNotBlank() }
}












































