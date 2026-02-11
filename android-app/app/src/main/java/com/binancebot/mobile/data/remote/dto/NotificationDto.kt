package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * DTOs for Notification API
 */

data class RegisterFcmTokenRequest(
    @SerializedName("token") val token: String,
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("device_type") val deviceType: String = "android",
    @SerializedName("client_type") val clientType: String = "android_app",
    @SerializedName("device_name") val deviceName: String? = null,
    @SerializedName("app_version") val appVersion: String? = null
)

data class RegisterFcmTokenResponse(
    @SerializedName("id") val id: String,
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("device_type") val deviceType: String,
    @SerializedName("client_type") val clientType: String,
    @SerializedName("device_name") val deviceName: String?,
    @SerializedName("app_version") val appVersion: String?,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String,
    @SerializedName("last_used_at") val lastUsedAt: String?
)

data class NotificationPreferencesDto(
    @SerializedName("trades_enabled") val tradesEnabled: Boolean = true,
    @SerializedName("alerts_enabled") val alertsEnabled: Boolean = true,
    @SerializedName("strategy_enabled") val strategyEnabled: Boolean = true,
    @SerializedName("system_enabled") val systemEnabled: Boolean = false,
    @SerializedName("sound_enabled") val soundEnabled: Boolean = true,
    @SerializedName("vibration_enabled") val vibrationEnabled: Boolean = true,
    @SerializedName("trade_pnl_threshold") val tradePnLThreshold: Double = 100.0,
    @SerializedName("alert_priority") val alertPriority: Int = 0
)

data class NotificationDto(
    @SerializedName("id") val id: String,
    @SerializedName("type") val type: String,
    @SerializedName("category") val category: String,
    @SerializedName("title") val title: String,
    @SerializedName("message") val message: String,
    @SerializedName("timestamp") val timestamp: Long,
    @SerializedName("read") val read: Boolean = false,
    @SerializedName("data") val data: Map<String, Any>? = null,
    @SerializedName("action_url") val actionUrl: String? = null,
    @SerializedName("priority") val priority: Int = 0
)

data class NotificationHistoryResponseDto(
    @SerializedName("notifications") val notifications: List<NotificationDto>,
    @SerializedName("total") val total: Int,
    @SerializedName("unread_count") val unreadCount: Int
)





