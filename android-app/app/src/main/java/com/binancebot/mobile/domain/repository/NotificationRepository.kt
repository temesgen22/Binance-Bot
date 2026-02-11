package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.domain.model.Notification
import com.binancebot.mobile.data.remote.dto.NotificationPreferencesDto

interface NotificationRepository {
    suspend fun registerFcmToken(
        fcmToken: String, 
        deviceId: String,
        deviceName: String? = null,
        appVersion: String? = null
    ): Result<Unit>
    suspend fun updateNotificationPreferences(preferences: NotificationPreferencesDto): Result<NotificationPreferencesDto>
    suspend fun getNotificationHistory(
        limit: Int = 50,
        offset: Int = 0,
        category: String? = null,
        type: String? = null
    ): Result<Pair<List<Notification>, Int>> // Returns (notifications, unreadCount)
    suspend fun markNotificationAsRead(notificationId: String): Result<Unit>
    suspend fun deleteNotification(notificationId: String): Result<Unit>
}





