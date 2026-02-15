package com.binancebot.mobile.util

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.binancebot.mobile.R
import com.binancebot.mobile.data.local.dao.NotificationDao
import com.binancebot.mobile.data.local.entities.NotificationEntity
import com.binancebot.mobile.presentation.MainActivity
import com.binancebot.mobile.presentation.navigation.Screen
import com.google.gson.Gson
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Notification Manager for handling push notifications
 */
@Singleton
class NotificationManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val notificationDao: NotificationDao
) {
    private val scope = CoroutineScope(Dispatchers.IO)
    companion object {
        private const val CHANNEL_ID_TRADES = "trades_channel"
        private const val CHANNEL_ID_ALERTS = "alerts_channel"
        private const val CHANNEL_ID_STRATEGIES = "strategies_channel"
        private const val CHANNEL_ID_SYSTEM = "system_channel"
        private const val CHANNEL_ID_PRICE_ALERTS = "price_alerts_channel"
        
        private const val NOTIFICATION_ID_TRADE = 1000
        private const val NOTIFICATION_ID_ALERT = 2000
        private const val NOTIFICATION_ID_STRATEGY = 4000
        private const val NOTIFICATION_ID_SYSTEM = 3000
    }
    
    init {
        createNotificationChannels()
    }
    
    /**
     * Create notification channels for Android O+
     */
    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager =
                context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            
            // Trades Channel
            val tradesChannel = NotificationChannel(
                CHANNEL_ID_TRADES,
                "Trades",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notifications for trade executions"
                enableVibration(true)
            }
            
            // Alerts Channel
            val alertsChannel = NotificationChannel(
                CHANNEL_ID_ALERTS,
                "Alerts",
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "Risk alerts and warnings"
                enableVibration(true)
            }
            
            // Strategies Channel
            val strategiesChannel = NotificationChannel(
                CHANNEL_ID_STRATEGIES,
                "Strategies",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Strategy start/stop and status notifications"
                enableVibration(true)
            }
            
            // System Channel
            val systemChannel = NotificationChannel(
                CHANNEL_ID_SYSTEM,
                "System",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "System notifications"
            }
            
            // Price Alerts Channel (Binance-style price cross notifications)
            val priceAlertsChannel = NotificationChannel(
                CHANNEL_ID_PRICE_ALERTS,
                "Price Alerts",
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "When price crosses your target"
                enableVibration(true)
            }
            
            notificationManager.createNotificationChannel(tradesChannel)
            notificationManager.createNotificationChannel(alertsChannel)
            notificationManager.createNotificationChannel(strategiesChannel)
            notificationManager.createNotificationChannel(systemChannel)
            notificationManager.createNotificationChannel(priceAlertsChannel)
        }
    }
    
    /**
     * Show trade notification with rich content and actions
     */
    fun showTradeNotification(
        title: String,
        message: String,
        tradeId: String? = null,
        expandedText: String? = null,
        data: Map<String, Any>? = null
    ) {
        val notificationId = UUID.randomUUID().toString()
        val actionUrl = tradeId?.let { "trades?trade_id=$it" }
        
        // Save to database
        scope.launch {
            notificationDao.insertNotification(
                NotificationEntity(
                    id = notificationId,
                    type = "trade",
                    category = "trade_executed",
                    title = title,
                    message = message,
                    timestamp = System.currentTimeMillis(),
                    read = false,
                    data = data?.let { Gson().toJson(it) },
                    actionUrl = actionUrl,
                    priority = NotificationCompat.PRIORITY_HIGH
                )
            )
        }
        
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            putExtra("trade_id", tradeId)
            putExtra("notification_id", notificationId)
            putExtra("deep_link", actionUrl)
        }
        
        val pendingIntent = PendingIntent.getActivity(
            context,
            notificationId.hashCode(),
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        val builder = NotificationCompat.Builder(context, CHANNEL_ID_TRADES)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setStyle(
                if (expandedText != null) {
                    NotificationCompat.BigTextStyle().bigText(expandedText)
                } else {
                    NotificationCompat.BigTextStyle().bigText(message)
                }
            )
        
        // Add action buttons
        tradeId?.let {
            val viewIntent = Intent(context, com.binancebot.mobile.service.NotificationActionReceiver::class.java).apply {
                action = com.binancebot.mobile.service.NotificationActionReceiver.ACTION_VIEW_TRADE
                putExtra("trade_id", it)
                putExtra("notification_id", NOTIFICATION_ID_TRADE + (it.hashCode()))
            }
            val viewPendingIntent = PendingIntent.getBroadcast(
                context,
                (it + "_view").hashCode(),
                viewIntent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            builder.addAction(
                android.R.drawable.ic_menu_view,
                "View Trade",
                viewPendingIntent
            )
        }
        
        NotificationManagerCompat.from(context).notify(
            NOTIFICATION_ID_TRADE + (tradeId?.hashCode() ?: 0),
            builder.build()
        )
    }
    
    /**
     * Show alert notification (risk alerts, strategy alerts)
     */
    fun showAlertNotification(
        title: String,
        message: String,
        alertType: String? = null,
        category: String = "risk_alert",
        expandedText: String? = null,
        actionUrl: String? = null,
        data: Map<String, Any>? = null
    ) {
        val notificationId = UUID.randomUUID().toString()
        val deepLink = actionUrl ?: when (alertType) {
            "risk_alert" -> Screen.RiskManagement.route
            "strategy_alert" -> Screen.Strategies.route
            "price_alert" -> Screen.PriceAlerts.route
            else -> null
        }
        
        // Save to database
        scope.launch {
            notificationDao.insertNotification(
                NotificationEntity(
                    id = notificationId,
                    type = "alert",
                    category = category,
                    title = title,
                    message = message,
                    timestamp = System.currentTimeMillis(),
                    read = false,
                    data = data?.let { Gson().toJson(it) },
                    actionUrl = deepLink,
                    priority = NotificationCompat.PRIORITY_DEFAULT
                )
            )
        }
        
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            putExtra("alert_type", alertType)
            putExtra("notification_id", notificationId)
            putExtra("deep_link", deepLink)
        }
        
        val pendingIntent = PendingIntent.getActivity(
            context,
            notificationId.hashCode(),
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        val builder = NotificationCompat.Builder(context, CHANNEL_ID_ALERTS)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setStyle(
                if (expandedText != null) {
                    NotificationCompat.BigTextStyle().bigText(expandedText)
                } else {
                    NotificationCompat.BigTextStyle().bigText(message)
                }
            )
        
        // Add action button
        deepLink?.let {
            val viewIntent = Intent(context, com.binancebot.mobile.service.NotificationActionReceiver::class.java).apply {
                action = com.binancebot.mobile.service.NotificationActionReceiver.ACTION_VIEW_STRATEGY
                putExtra("deep_link", it)
                putExtra("notification_id", NOTIFICATION_ID_ALERT + (alertType?.hashCode() ?: 0))
            }
            val viewPendingIntent = PendingIntent.getBroadcast(
                context,
                (it + "_view").hashCode(),
                viewIntent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            builder.addAction(
                android.R.drawable.ic_menu_view,
                "View Details",
                viewPendingIntent
            )
        }
        
        NotificationManagerCompat.from(context).notify(
            NOTIFICATION_ID_ALERT + (alertType?.hashCode() ?: 0),
            builder.build()
        )
    }
    
    /**
     * Show price alert notification (Binance-style: price crossed target).
     * Uses price_alerts_channel and deep link to Price Alerts screen.
     */
    fun showPriceAlertNotification(
        title: String,
        message: String,
        data: Map<String, String>? = null
    ) {
        val notificationId = UUID.randomUUID().toString()
        val deepLink = Screen.PriceAlerts.route
        scope.launch {
            notificationDao.insertNotification(
                NotificationEntity(
                    id = notificationId,
                    type = "price_alert",
                    category = "price_alert",
                    title = title,
                    message = message,
                    timestamp = System.currentTimeMillis(),
                    read = false,
                    data = data?.let { Gson().toJson(it) },
                    actionUrl = deepLink,
                    priority = NotificationCompat.PRIORITY_DEFAULT
                )
            )
        }
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            putExtra("deep_link", deepLink)
            putExtra("notification_id", notificationId)
            putExtra("type", "price_alert")
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            notificationId.hashCode(),
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val builder = NotificationCompat.Builder(context, CHANNEL_ID_PRICE_ALERTS)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(title)
            .setContentText(message)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
        NotificationManagerCompat.from(context).notify(
            notificationId.hashCode().and(0x7FFFFFFF),
            builder.build()
        )
    }
    
    /**
     * Show strategy notification
     */
    fun showStrategyNotification(
        title: String,
        message: String,
        strategyId: String? = null,
        category: String = "strategy_update",
        expandedText: String? = null,
        data: Map<String, Any>? = null
    ) {
        Log.d("NotificationManager", "showStrategyNotification called: title=$title, message=$message, strategyId=$strategyId, category=$category")
        val notificationId = UUID.randomUUID().toString()
        val actionUrl = strategyId?.let { "strategy_details/$it" }
        
        // Save to database
        scope.launch {
            notificationDao.insertNotification(
                NotificationEntity(
                    id = notificationId,
                    type = "strategy",
                    category = category,
                    title = title,
                    message = message,
                    timestamp = System.currentTimeMillis(),
                    read = false,
                    data = data?.let { Gson().toJson(it) },
                    actionUrl = actionUrl,
                    priority = NotificationCompat.PRIORITY_DEFAULT
                )
            )
        }
        
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            putExtra("strategy_id", strategyId)
            putExtra("notification_id", notificationId)
            putExtra("deep_link", actionUrl)
        }
        
        val pendingIntent = PendingIntent.getActivity(
            context,
            notificationId.hashCode(),
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        val builder = NotificationCompat.Builder(context, CHANNEL_ID_STRATEGIES)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setStyle(
                if (expandedText != null) {
                    NotificationCompat.BigTextStyle().bigText(expandedText)
                } else {
                    NotificationCompat.BigTextStyle().bigText(message)
                }
            )
        
        // Add action button
        strategyId?.let {
            val viewIntent = Intent(context, com.binancebot.mobile.service.NotificationActionReceiver::class.java).apply {
                action = com.binancebot.mobile.service.NotificationActionReceiver.ACTION_VIEW_STRATEGY
                putExtra("strategy_id", it)
                putExtra("notification_id", NOTIFICATION_ID_STRATEGY + (it.hashCode()))
            }
            val viewPendingIntent = PendingIntent.getBroadcast(
                context,
                (it + "_view").hashCode(),
                viewIntent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            builder.addAction(
                android.R.drawable.ic_menu_view,
                "View Strategy",
                viewPendingIntent
            )
        }
        
        val systemNotificationId = NOTIFICATION_ID_STRATEGY + (strategyId?.hashCode() ?: 0)
        Log.d("NotificationManager", "Displaying strategy notification with system ID: $systemNotificationId")
        NotificationManagerCompat.from(context).notify(
            systemNotificationId,
            builder.build()
        )
        Log.d("NotificationManager", "Strategy notification displayed successfully")
    }
    
    /**
     * Show system notification
     */
    fun showSystemNotification(
        title: String,
        message: String,
        category: String = "system",
        expandedText: String? = null,
        actionUrl: String? = null
    ) {
        val notificationId = UUID.randomUUID().toString()
        
        // Save to database
        scope.launch {
            notificationDao.insertNotification(
                NotificationEntity(
                    id = notificationId,
                    type = "system",
                    category = category,
                    title = title,
                    message = message,
                    timestamp = System.currentTimeMillis(),
                    read = false,
                    data = null,
                    actionUrl = actionUrl,
                    priority = NotificationCompat.PRIORITY_LOW
                )
            )
        }
        
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            putExtra("notification_id", notificationId)
            putExtra("deep_link", actionUrl)
        }
        
        val pendingIntent = PendingIntent.getActivity(
            context,
            notificationId.hashCode(),
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        val builder = NotificationCompat.Builder(context, CHANNEL_ID_SYSTEM)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
        
        if (expandedText != null) {
            builder.setStyle(NotificationCompat.BigTextStyle().bigText(expandedText))
        }
        
        NotificationManagerCompat.from(context).notify(
            NOTIFICATION_ID_SYSTEM + notificationId.hashCode(),
            builder.build()
        )
    }
    
    /**
     * Cancel all notifications
     */
    fun cancelAllNotifications() {
        NotificationManagerCompat.from(context).cancelAll()
    }
    
    /**
     * Cancel specific notification
     */
    fun cancelNotification(notificationId: Int) {
        NotificationManagerCompat.from(context).cancel(notificationId)
    }
}



