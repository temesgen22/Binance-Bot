package com.binancebot.mobile.service

import android.os.Build
import com.binancebot.mobile.util.AppLogger
import com.binancebot.mobile.BuildConfig
import com.binancebot.mobile.domain.repository.NotificationRepository
import com.binancebot.mobile.util.NotificationManager
import com.binancebot.mobile.util.PreferencesManager
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Firebase Cloud Messaging Service
 * Handles incoming push notifications and FCM token management
 */
@AndroidEntryPoint
class BinanceBotFirebaseMessagingService : FirebaseMessagingService() {
    
    @Inject
    lateinit var notificationManager: NotificationManager
    
    @Inject
    lateinit var notificationRepository: NotificationRepository

    @Inject
    lateinit var preferencesManager: PreferencesManager
    
    private val scope = CoroutineScope(Dispatchers.IO)
    
    override fun onNewToken(token: String) {
        super.onNewToken(token)
        AppLogger.d("FCM", "New FCM token: $token")
        
        // Register token with backend
        scope.launch {
            try {
                val deviceId = android.provider.Settings.Secure.getString(
                    contentResolver,
                    android.provider.Settings.Secure.ANDROID_ID
                )
                
                // Get device name (manufacturer + model)
                val deviceName = "${Build.MANUFACTURER} ${Build.MODEL}"
                
                // Get app version
                val appVersion = BuildConfig.VERSION_NAME
                
                notificationRepository.registerFcmToken(
                    fcmToken = token, 
                    deviceId = deviceId,
                    deviceName = deviceName,
                    appVersion = appVersion
                )
                    .onSuccess {
                        AppLogger.d("FCM", "Token registered successfully for device: $deviceId ($deviceName)")
                    }
                    .onFailure { e ->
                        AppLogger.e("FCM", "Failed to register token", e)
                    }
            } catch (e: Exception) {
                AppLogger.e("FCM", "Failed to register token", e)
            }
        }
    }
    
    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        super.onMessageReceived(remoteMessage)
        AppLogger.d("FCM", "Message received from: ${remoteMessage.from}")
        
        // Handle notification based on what's present in the message
        // Priority: notification payload > data-only payload
        // This prevents duplicate notifications when both are present
        
        val notification = remoteMessage.notification
        val data = remoteMessage.data
        
        if (notification != null) {
            // Message contains notification payload - use it (has title/body)
            AppLogger.d("FCM", "Message notification payload: ${notification.title} - ${notification.body}")
            handleNotificationMessage(notification, data)
        } else if (data.isNotEmpty()) {
            // Data-only message - handle it separately
            AppLogger.d("FCM", "Message data payload: $data")
            handleDataMessage(data)
        }
    }

    /**
     * Check user preferences before showing push. Only show if notifications are enabled
     * and the specific type (trade / alert / strategy / system) is enabled.
     */
    private fun handleDataMessage(data: Map<String, String>) {
        scope.launch {
            val notificationsEnabled = preferencesManager.notificationsEnabled.first()
            if (!notificationsEnabled) {
                AppLogger.d("FCM", "Notifications disabled in settings, skipping push")
                return@launch
            }
            val type = data["type"] ?: "system"
            val typeAllowed = when (type) {
                "trade" -> preferencesManager.tradesEnabled.first()
                "alert", "price_alert" -> preferencesManager.alertsEnabled.first()
                "strategy" -> preferencesManager.strategyEnabled.first()
                else -> preferencesManager.systemEnabled.first()
            }
            if (!typeAllowed) {
                AppLogger.d("FCM", "Notification type '$type' disabled in settings, skipping push")
                return@launch
            }
            showDataMessage(data)
        }
    }

    private fun showDataMessage(data: Map<String, String>) {
        val type = data["type"] ?: "system"
        val category = data["category"] ?: "system"
        val title = data["title"] ?: "Notification"
        val message = data["message"] ?: ""
        val actionUrl = data["action_url"]
        
        when (type) {
            "trade" -> {
                notificationManager.showTradeNotification(
                    title = title,
                    message = message,
                    tradeId = data["trade_id"],
                    expandedText = data["expanded_text"],
                    data = data
                )
            }
            "alert" -> {
                notificationManager.showAlertNotification(
                    title = title,
                    message = message,
                    alertType = data["alert_type"],
                    category = category,
                    expandedText = data["expanded_text"],
                    actionUrl = actionUrl,
                    data = data
                )
            }
            "price_alert" -> {
                notificationManager.showPriceAlertNotification(
                    title = title,
                    message = message,
                    data = data
                )
            }
            "strategy" -> {
                notificationManager.showStrategyNotification(
                    title = title,
                    message = message,
                    strategyId = data["strategy_id"],
                    category = category,
                    expandedText = data["expanded_text"],
                    data = data
                )
            }
            else -> {
                notificationManager.showSystemNotification(
                    title = title,
                    message = message,
                    category = category,
                    expandedText = data["expanded_text"],
                    actionUrl = actionUrl
                )
            }
        }
    }
    
    private fun handleNotificationMessage(
        notification: com.google.firebase.messaging.RemoteMessage.Notification,
        data: Map<String, String>
    ) {
        scope.launch {
            val notificationsEnabled = preferencesManager.notificationsEnabled.first()
            if (!notificationsEnabled) {
                AppLogger.d("FCM", "Notifications disabled in settings, skipping push")
                return@launch
            }
            val type = data["type"] ?: "system"
            val typeAllowed = when (type) {
                "trade" -> preferencesManager.tradesEnabled.first()
                "alert", "price_alert" -> preferencesManager.alertsEnabled.first()
                "strategy" -> preferencesManager.strategyEnabled.first()
                else -> preferencesManager.systemEnabled.first()
            }
            if (!typeAllowed) {
                AppLogger.d("FCM", "Notification type '$type' disabled in settings, skipping push")
                return@launch
            }
            showNotificationMessage(notification, data)
        }
    }

    private fun showNotificationMessage(
        notification: com.google.firebase.messaging.RemoteMessage.Notification,
        data: Map<String, String>
    ) {
        val type = data["type"] ?: "system"
        val category = data["category"] ?: "system"
        
        when (type) {
            "trade" -> {
                notificationManager.showTradeNotification(
                    title = notification.title ?: "Trade Notification",
                    message = notification.body ?: "",
                    tradeId = data["trade_id"],
                    data = data
                )
            }
            "alert" -> {
                notificationManager.showAlertNotification(
                    title = notification.title ?: "Alert",
                    message = notification.body ?: "",
                    alertType = data["alert_type"],
                    category = category,
                    actionUrl = data["action_url"],
                    data = data
                )
            }
            "price_alert" -> {
                notificationManager.showPriceAlertNotification(
                    title = notification.title ?: "Price Alert",
                    message = notification.body ?: "",
                    data = data
                )
            }
            "strategy" -> {
                notificationManager.showStrategyNotification(
                    title = notification.title ?: "Strategy Update",
                    message = notification.body ?: "",
                    strategyId = data["strategy_id"],
                    category = category,
                    data = data
                )
            }
            else -> {
                notificationManager.showSystemNotification(
                    title = notification.title ?: "System Notification",
                    message = notification.body ?: "",
                    category = category
                )
            }
        }
    }
}

