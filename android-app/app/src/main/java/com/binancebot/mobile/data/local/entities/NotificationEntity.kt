package com.binancebot.mobile.data.local.entities

import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.core.app.NotificationCompat

/**
 * Room entity for Notification.
 * Stores notification history locally.
 */
@Entity(tableName = "notifications")
data class NotificationEntity(
    @PrimaryKey val id: String,
    val type: String, // "trade", "alert", "strategy", "system"
    val category: String, // "trade_executed", "risk_alert", etc.
    val title: String,
    val message: String,
    val timestamp: Long,
    val read: Boolean = false,
    val data: String? = null, // JSON string for additional data
    val actionUrl: String? = null, // Deep link URL
    val priority: Int = NotificationCompat.PRIORITY_DEFAULT
) {
    fun toDomain(): com.binancebot.mobile.domain.model.Notification {
        return com.binancebot.mobile.domain.model.Notification(
            id = id,
            type = type,
            category = category,
            title = title,
            message = message,
            timestamp = timestamp,
            read = read,
            data = data,
            actionUrl = actionUrl,
            priority = priority
        )
    }
    
    companion object {
        fun fromDomain(notification: com.binancebot.mobile.domain.model.Notification): NotificationEntity {
            return NotificationEntity(
                id = notification.id,
                type = notification.type,
                category = notification.category,
                title = notification.title,
                message = notification.message,
                timestamp = notification.timestamp,
                read = notification.read,
                data = notification.data,
                actionUrl = notification.actionUrl,
                priority = notification.priority
            )
        }
    }
}





