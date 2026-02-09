package com.binancebot.mobile.util

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.binancebot.mobile.R
import com.binancebot.mobile.presentation.MainActivity
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Notification Manager for handling push notifications
 */
@Singleton
class NotificationManager @Inject constructor(
    @ApplicationContext private val context: Context
) {
    companion object {
        private const val CHANNEL_ID_TRADES = "trades_channel"
        private const val CHANNEL_ID_ALERTS = "alerts_channel"
        private const val CHANNEL_ID_SYSTEM = "system_channel"
        
        private const val NOTIFICATION_ID_TRADE = 1000
        private const val NOTIFICATION_ID_ALERT = 2000
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
                description = "Risk alerts and strategy notifications"
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
            
            notificationManager.createNotificationChannel(tradesChannel)
            notificationManager.createNotificationChannel(alertsChannel)
            notificationManager.createNotificationChannel(systemChannel)
        }
    }
    
    /**
     * Show trade notification
     */
    fun showTradeNotification(
        title: String,
        message: String,
        tradeId: String? = null
    ) {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            putExtra("trade_id", tradeId)
        }
        
        val pendingIntent = PendingIntent.getActivity(
            context,
            0,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        val notification = NotificationCompat.Builder(context, CHANNEL_ID_TRADES)
            .setSmallIcon(android.R.drawable.ic_dialog_info) // TODO: Add custom icon
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()
        
        NotificationManagerCompat.from(context).notify(
            NOTIFICATION_ID_TRADE + (tradeId?.hashCode() ?: 0),
            notification
        )
    }
    
    /**
     * Show alert notification
     */
    fun showAlertNotification(
        title: String,
        message: String,
        alertType: String? = null
    ) {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            putExtra("alert_type", alertType)
        }
        
        val pendingIntent = PendingIntent.getActivity(
            context,
            0,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        val notification = NotificationCompat.Builder(context, CHANNEL_ID_ALERTS)
            .setSmallIcon(android.R.drawable.ic_dialog_alert) // TODO: Add custom icon
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()
        
        NotificationManagerCompat.from(context).notify(
            NOTIFICATION_ID_ALERT + (alertType?.hashCode() ?: 0),
            notification
        )
    }
    
    /**
     * Show system notification
     */
    fun showSystemNotification(
        title: String,
        message: String
    ) {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        
        val pendingIntent = PendingIntent.getActivity(
            context,
            0,
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        val notification = NotificationCompat.Builder(context, CHANNEL_ID_SYSTEM)
            .setSmallIcon(android.R.drawable.ic_dialog_info) // TODO: Add custom icon
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()
        
        NotificationManagerCompat.from(context).notify(
            NOTIFICATION_ID_SYSTEM,
            notification
        )
    }
    
    /**
     * Cancel all notifications
     */
    fun cancelAllNotifications() {
        NotificationManagerCompat.from(context).cancelAll()
    }
}


