package com.binancebot.mobile.domain.model

import androidx.core.app.NotificationCompat

/**
 * Domain model for Notification.
 */
data class Notification(
    val id: String,
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
    val isTrade: Boolean
        get() = type == "trade"
    
    val isAlert: Boolean
        get() = type == "alert"
    
    val isStrategy: Boolean
        get() = type == "strategy"
    
    val isSystem: Boolean
        get() = type == "system"
}





