package com.binancebot.mobile.data.remote.websocket

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
            return
        }
        
        val token = tokenManager.getAccessToken() ?: run {
            scope.launch {
                _updates.tryEmit(UpdateMessage.Error("Not authenticated"))
            }
            return
        }
        
        val request = Request.Builder()
            .url("$url?token=$token")
            .build()
        
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                isConnected = true
                // ✅ Use tryEmit from coroutine scope
                scope.launch {
                    _updates.tryEmit(UpdateMessage.Connected)
                }
            }
            
            override fun onMessage(webSocket: WebSocket, text: String) {
                // ✅ Use tryEmit for thread-safe emission
                scope.launch {
                    try {
                        // Parse as generic JSON object first (Gson doesn't support sealed classes directly)
                        val jsonObject = gson.fromJson(text, com.google.gson.JsonObject::class.java)
                        val messageType = jsonObject.get("type")?.asString ?: "unknown"
                        
                        val message = when (messageType) {
                            "connected" -> UpdateMessage.Connected
                            "disconnected" -> UpdateMessage.Disconnected
                            "strategy_update" -> {
                                val data = jsonObject.getAsJsonObject("data")
                                UpdateMessage.StrategyUpdate(
                                    strategyId = data.get("strategyId")?.asString ?: "",
                                    status = data.get("status")?.asString ?: "",
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
                // ✅ Use tryEmit for error signal
                scope.launch {
                    _updates.tryEmit(UpdateMessage.Error(t.message ?: "Connection failed"))
                }
                // Attempt reconnection
                reconnect(url)
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
    data class Error(val message: String) : UpdateMessage()
}

