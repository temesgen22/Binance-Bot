package com.binancebot.mobile.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationManagerCompat
import com.binancebot.mobile.presentation.MainActivity

/**
 * BroadcastReceiver for handling notification actions
 * Handles actions like "View Trade", "Stop Strategy", etc.
 */
class NotificationActionReceiver : BroadcastReceiver() {
    
    companion object {
        const val ACTION_VIEW_TRADE = "com.binancebot.mobile.ACTION_VIEW_TRADE"
        const val ACTION_VIEW_STRATEGY = "com.binancebot.mobile.ACTION_VIEW_STRATEGY"
        const val ACTION_DISMISS = "com.binancebot.mobile.ACTION_DISMISS"
    }
    
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            ACTION_VIEW_TRADE -> {
                val tradeId = intent.getStringExtra("trade_id")
                val notificationId = intent.getIntExtra("notification_id", -1)
                
                // Dismiss notification
                if (notificationId != -1) {
                    NotificationManagerCompat.from(context).cancel(notificationId)
                }
                
                // Navigate to trade details
                val navIntent = Intent(context, MainActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                    putExtra("trade_id", tradeId)
                    putExtra("deep_link", "trades?trade_id=$tradeId")
                }
                context.startActivity(navIntent)
            }
            
            ACTION_VIEW_STRATEGY -> {
                val strategyId = intent.getStringExtra("strategy_id")
                val notificationId = intent.getIntExtra("notification_id", -1)
                
                // Dismiss notification
                if (notificationId != -1) {
                    NotificationManagerCompat.from(context).cancel(notificationId)
                }
                
                // Navigate to strategy details
                val navIntent = Intent(context, MainActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                    putExtra("strategy_id", strategyId)
                    putExtra("deep_link", "strategy_details/$strategyId")
                }
                context.startActivity(navIntent)
            }
            
            ACTION_DISMISS -> {
                val notificationId = intent.getIntExtra("notification_id", -1)
                if (notificationId != -1) {
                    NotificationManagerCompat.from(context).cancel(notificationId)
                }
            }
        }
    }
}

