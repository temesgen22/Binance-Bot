package com.binancebot.mobile.data.remote.websocket

import android.util.Log
import com.binancebot.mobile.util.TokenManager
import com.google.gson.Gson
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import okhttp3.*
import javax.inject.Inject
import javax.inject.Singleton

/**
 * WebSocket Manager for real-time updates.
 * 
 * ✅ CRITICAL FIX: Uses coroutine scope with tryEmit/launch for thread-safe emissions.
 */
@Singleton
class WebSocketManager @Inject constructor(
    private val tokenManager: TokenManager
) {
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var webSocket: WebSocket? = null
    private val client = OkHttpClient()
    private val gson = Gson()
    
    private val _updates = MutableSharedFlow<UpdateMessage>(
        replay = 0,
        extraBufferCapacity = 64
    )
    val updates: SharedFlow<UpdateMessage> = _updates.asSharedFlow()
    
    @Volatile
    private var isConnected = false
    
    fun connect(url: String) {
        if (isConnected) {
            Log.d("WebSocketManager", "WebSocket already connected, skipping")
            return
        }
        
        Log.d("WebSocketManager", "Attempting to connect to WebSocket: $url")
        val token = tokenManager.getAccessToken() ?: run {
            Log.e("WebSocketManager", "No access token available, cannot connect")
            scope.launch {
                _updates.tryEmit(UpdateMessage.Error("Not authenticated"))
            }
            return
        }
        
        val request = Request.Builder()
            .url("$url?token=$token")
            .build()
        
        Log.d("WebSocketManager", "Creating WebSocket connection...")
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                isConnected = true
                Log.d("WebSocketManager", "WebSocket connection opened successfully")
                // ✅ Use tryEmit from coroutine scope
                scope.launch {
                    _updates.tryEmit(UpdateMessage.Connected)
                }
            }
            
            override fun onMessage(webSocket: WebSocket, text: String) {
                Log.d("WebSocketManager", "Received WebSocket message: $text")
                // ✅ Use tryEmit for thread-safe emission
                scope.launch {
                    try {
                        // Parse as generic JSON object first (Gson doesn't support sealed classes directly)
                        val jsonObject = gson.fromJson(text, com.google.gson.JsonObject::class.java)
                        val messageType = jsonObject.get("type")?.asString ?: "unknown"
                        Log.d("WebSocketManager", "Parsed message type: $messageType")
                        
                        val message = when (messageType) {
                            "connected" -> UpdateMessage.Connected
                            "disconnected" -> UpdateMessage.Disconnected
                            "strategy_update" -> {
                                val data = jsonObject.getAsJsonObject("data")
                                val strategyId = data.get("strategyId")?.asString ?: ""
                                val status = data.get("status")?.asString ?: ""
                                Log.d("WebSocketManager", "Creating StrategyUpdate: strategyId=$strategyId, status=$status")
                                UpdateMessage.StrategyUpdate(
                                    strategyId = strategyId,
                                    status = status,
                                    data = data.entrySet().associate { it.key to it.value.asString }
                                )
                            }
                            "trade_update" -> {
                                val data = jsonObject.getAsJsonObject("data")
                                UpdateMessage.TradeUpdate(
                                    tradeId = data.get("tradeId")?.asString ?: "",
                                    strategyId = data.get("strategyId")?.asString ?: "",
                                    data = data.entrySet().associate { it.key to it.value.asString }
                                )
                            }
                            "risk_alert" -> {
                                val data = jsonObject.getAsJsonObject("data")
                                UpdateMessage.RiskAlert(
                                    alertType = data.get("alertType")?.asString ?: "unknown",
                                    accountId = data.get("accountId")?.asString,
                                    currentValue = data.get("currentValue")?.asString,
                                    limitValue = data.get("limitValue")?.asString,
                                    message = data.get("message")?.asString ?: "Risk alert",
                                    data = data.entrySet().associate { it.key to it.value.asString }
                                )
                            }
                            "error" -> UpdateMessage.Error(
                                jsonObject.get("message")?.asString ?: "Unknown error"
                            )
                            else -> UpdateMessage.Error("Unknown message type: $messageType")
                        }
                        _updates.tryEmit(message)
                    } catch (e: Exception) {
                        _updates.tryEmit(UpdateMessage.Error("Failed to parse message: ${e.message}"))
                    }
                }
            }
            
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                isConnected = false
                val errorMessage = when {
                    response?.code == 404 -> "WebSocket endpoint not found (404). Backend WebSocket server not implemented yet."
                    response != null -> "WebSocket connection failed: ${response.code} ${response.message}"
                    else -> t.message ?: "Connection failed"
                }
                Log.e("WebSocketManager", errorMessage)
                // Don't emit error to avoid showing error notifications when WebSocket isn't available
                // Only emit if it's a real connection error (not 404)
                if (response?.code != 404) {
                    scope.launch {
                        _updates.tryEmit(UpdateMessage.Error(errorMessage))
                    }
                }
                // Don't attempt reconnection for 404 errors
                if (response?.code != 404) {
                    reconnect(url)
                }
            }
            
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                isConnected = false
                // ✅ Use tryEmit for disconnect signal
                scope.launch {
                    _updates.tryEmit(UpdateMessage.Disconnected)
                }
            }
        })
    }
    
    fun disconnect() {
        webSocket?.close(1000, "Client disconnect")
        webSocket = null
        isConnected = false
        scope.cancel()
    }
    
    private fun reconnect(url: String) {
        scope.launch {
            var delay = 1000L
            repeat(5) {
                delay(delay)
                if (!isConnected) {
                    connect(url)
                } else {
                    return@launch
                }
                delay *= 2 // Exponential backoff
            }
        }
    }
    
    fun send(message: String): Boolean {
        return webSocket?.send(message) ?: false
    }
}

/**
 * WebSocket update message types
 */
sealed class UpdateMessage {
    object Connected : UpdateMessage()
    object Disconnected : UpdateMessage()
    data class StrategyUpdate(
        val strategyId: String,
        val status: String,
        val data: Map<String, Any>? = null
    ) : UpdateMessage()
    data class TradeUpdate(
        val tradeId: String,
        val strategyId: String,
        val data: Map<String, Any>? = null
    ) : UpdateMessage()
    data class RiskAlert(
        val alertType: String,
        val accountId: String? = null,
        val currentValue: String? = null,
        val limitValue: String? = null,
        val message: String,
        val data: Map<String, Any>? = null
    ) : UpdateMessage()
    data class Error(val message: String) : UpdateMessage()
}

