package com.binancebot.mobile.util

import android.content.Context
import android.util.Log
import com.binancebot.mobile.data.remote.websocket.UpdateMessage
import com.binancebot.mobile.data.remote.websocket.WebSocketManager
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Notification Trigger Service
 * Listens to WebSocket updates and triggers notifications based on user preferences
 */
@Singleton
class NotificationTrigger @Inject constructor(
    @ApplicationContext private val context: Context,
    private val webSocketManager: WebSocketManager,
    private val notificationManager: NotificationManager,
    private val preferencesManager: PreferencesManager
) {
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var isListening = false
    
    fun startListening() {
        if (isListening) {
            Log.d("NotificationTrigger", "Already listening, skipping")
            return
        }
        isListening = true
        Log.d("NotificationTrigger", "Starting to listen for notifications")
        
        scope.launch {
            // Combine preferences with WebSocket updates
            combine(
                preferencesManager.notificationsEnabled,
                preferencesManager.tradesEnabled,
                preferencesManager.alertsEnabled,
                preferencesManager.strategyEnabled,
                webSocketManager.updates
            ) { notifications, trades, alerts, strategy, message ->
                Pair(
                    NotificationPreferences(notifications, trades, alerts, strategy),
                    message
                )
            }.collectLatest { (prefs, message) ->
                Log.d("NotificationTrigger", "Received message: ${message::class.simpleName}, Notifications enabled: ${prefs.notificationsEnabled}, Trades: ${prefs.tradesEnabled}, Alerts: ${prefs.alertsEnabled}, Strategy: ${prefs.strategyEnabled}")
                if (!prefs.notificationsEnabled) {
                    Log.d("NotificationTrigger", "Notifications disabled globally, skipping")
                    return@collectLatest
                }
                
                when (message) {
                    is UpdateMessage.TradeUpdate -> {
                        if (prefs.tradesEnabled) {
                            val tradeId = message.tradeId
                            val strategyId = message.strategyId
                            val symbol = message.data?.get("symbol") as? String ?: "Unknown"
                            val side = message.data?.get("side") as? String ?: "Unknown"
                            val quantity = message.data?.get("quantity") as? String ?: "0"
                            val price = message.data?.get("price") as? String ?: "0"
                            val pnl = message.data?.get("pnl") as? String
                            
                            val title = "Trade Executed"
                            val messageText = "$side $quantity $symbol @ $price"
                            val expandedText = if (pnl != null) {
                                "$messageText\nPnL: $pnl"
                            } else {
                                messageText
                            }
                            
                            notificationManager.showTradeNotification(
                                title = title,
                                message = messageText,
                                tradeId = tradeId,
                                expandedText = expandedText,
                                data = message.data
                            )
                        }
                    }
                    
                    is UpdateMessage.StrategyUpdate -> {
                        Log.d("NotificationTrigger", "Strategy update received: strategyId=${message.strategyId}, status=${message.status}, strategyEnabled=${prefs.strategyEnabled}")
                        if (prefs.strategyEnabled) {
                            val strategyId = message.strategyId
                            val status = message.status
                            
                            val title = when (status.lowercase()) {
                                "running", "started" -> "Strategy Started"
                                "stopped" -> "Strategy Stopped"
                                "error" -> "Strategy Error"
                                else -> "Strategy Update"
                            }
                            
                            val messageText = message.data?.get("message") as? String
                                ?: "Strategy $status"
                            
                            Log.d("NotificationTrigger", "Showing strategy notification: title=$title, message=$messageText")
                            notificationManager.showStrategyNotification(
                                title = title,
                                message = messageText,
                                strategyId = strategyId,
                                category = when (status.lowercase()) {
                                    "running", "started" -> "strategy_started"
                                    "stopped" -> "strategy_stopped"
                                    "error" -> "strategy_error"
                                    else -> "strategy_update"
                                },
                                data = message.data
                            )
                        } else {
                            Log.d("NotificationTrigger", "Strategy notifications disabled, skipping")
                        }
                    }
                    
                    is UpdateMessage.RiskAlert -> {
                        if (prefs.alertsEnabled) {
                            val alertType = message.alertType
                            val accountId = message.accountId
                            val currentValue = message.currentValue
                            val limitValue = message.limitValue
                            
                            val title = when (alertType.lowercase()) {
                                "daily_loss_limit" -> "Daily Loss Limit Reached"
                                "max_drawdown" -> "Max Drawdown Alert"
                                "circuit_breaker" -> "Circuit Breaker Activated"
                                "position_size_limit" -> "Position Size Limit Exceeded"
                                else -> "Risk Alert"
                            }
                            
                            val messageText = message.message
                            val expandedText = if (currentValue != null && limitValue != null) {
                                "$messageText\nCurrent: $currentValue / Limit: $limitValue"
                            } else {
                                messageText
                            }
                            
                            notificationManager.showAlertNotification(
                                title = title,
                                message = messageText,
                                alertType = alertType,
                                category = "risk_alert",
                                expandedText = expandedText,
                                actionUrl = "risk",
                                data = message.data
                            )
                        }
                    }
                    
                    is UpdateMessage.Error -> {
                        if (prefs.alertsEnabled) {
                            notificationManager.showAlertNotification(
                                title = "Connection Error",
                                message = message.message,
                                alertType = "error",
                                category = "system_error"
                            )
                        }
                    }
                    
                    is UpdateMessage.Connected -> {
                        // Optional: Show connection status notification
                        // notificationManager.showSystemNotification(
                        //     title = "Connected",
                        //     message = "WebSocket connection established"
                        // )
                    }
                    
                    is UpdateMessage.Disconnected -> {
                        // Optional: Show disconnection notification
                        // notificationManager.showSystemNotification(
                        //     title = "Disconnected",
                        //     message = "WebSocket connection lost"
                        // )
                    }
                }
            }
        }
    }
    
    fun stopListening() {
        isListening = false
    }
    
    private data class NotificationPreferences(
        val notificationsEnabled: Boolean,
        val tradesEnabled: Boolean,
        val alertsEnabled: Boolean,
        val strategyEnabled: Boolean
    )
}

