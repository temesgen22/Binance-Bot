package com.binancebot.mobile.data.remote.websocket

import com.binancebot.mobile.util.AppLogger
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
    
    @Volatile
    private var isConnecting = false
    
    fun connect(url: String) {
        if (isConnected) {
            AppLogger.d("WebSocketManager", "WebSocket already connected, skipping")
            return
        }
        if (isConnecting) {
            AppLogger.d("WebSocketManager", "WebSocket connection already in progress, skipping duplicate attempt")
            return
        }
        isConnecting = true
        AppLogger.d("WebSocketManager", "Attempting to connect to WebSocket: $url")
        val token = tokenManager.getAccessToken() ?: run {
            isConnecting = false
            AppLogger.e("WebSocketManager", "No access token available, cannot connect")
            scope.launch {
                _updates.tryEmit(UpdateMessage.Error("Not authenticated"))
            }
            return
        }
        
        val request = Request.Builder()
            .url("$url?token=$token")
            .build()
        
        AppLogger.d("WebSocketManager", "Creating WebSocket connection...")
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                isConnecting = false
                isConnected = true
                AppLogger.d("WebSocketManager", "WebSocket connection opened successfully")
                // ✅ Use tryEmit from coroutine scope
                scope.launch {
                    _updates.tryEmit(UpdateMessage.Connected)
                }
            }
            
            override fun onMessage(webSocket: WebSocket, text: String) {
                AppLogger.d("WebSocketManager", "Received WebSocket message: $text")
                // ✅ Use tryEmit for thread-safe emission
                scope.launch {
                    try {
                        // Parse as generic JSON object first (Gson doesn't support sealed classes directly)
                        val jsonObject = gson.fromJson(text, com.google.gson.JsonObject::class.java)
                        val messageType = jsonObject.get("type")?.asString ?: "unknown"
                        AppLogger.d("WebSocketManager", "Parsed message type: $messageType")
                        
                        val message = when (messageType) {
                            "connected" -> UpdateMessage.Connected
                            "disconnected" -> UpdateMessage.Disconnected
                            "position_update" -> {
                                val symbol = jsonObject.get("symbol")?.asString ?: ""
                                val strategyIdRaw = jsonObject.get("strategy_id")?.takeIf { !it.isJsonNull }?.asString
                                    ?: jsonObject.get("strategyId")?.takeIf { !it.isJsonNull }?.asString
                                // Backend sends strategy_id=null for manual/unowned positions; use synthetic key so we don't drop the update
                                val strategyId = if (strategyIdRaw.isNullOrBlank()) "manual_$symbol" else strategyIdRaw
                                val strategyName = try { jsonObject.get("strategy_name")?.takeIf { !it.isJsonNull }?.asString } catch (_: Exception) { null }
                                val accountId = jsonObject.get("account_id")?.asString ?: "default"
                                val positionSize = try { jsonObject.get("position_size")?.takeIf { !it.isJsonNull }?.getAsDouble() ?: 0.0 } catch (_: Exception) { 0.0 }
                                val entryPrice = try { jsonObject.get("entry_price")?.takeIf { !it.isJsonNull }?.getAsDouble() } catch (_: Exception) { null }
                                val unrealizedPnl = try { jsonObject.get("unrealized_pnl")?.takeIf { !it.isJsonNull }?.getAsDouble() } catch (_: Exception) { null }
                                val positionSide = try { jsonObject.get("position_side")?.takeIf { !it.isJsonNull }?.getAsString() } catch (_: Exception) { null }
                                val currentPrice = try { jsonObject.get("current_price")?.takeIf { !it.isJsonNull }?.getAsDouble() } catch (_: Exception) { null }
                                val leverage = try { jsonObject.get("leverage")?.takeIf { !it.isJsonNull }?.getAsInt() } catch (_: Exception) { null }
                                val liquidationPrice = try { jsonObject.get("liquidation_price")?.takeIf { !it.isJsonNull }?.getAsDouble() } catch (_: Exception) { null }
                                val initialMargin = try { jsonObject.get("initial_margin")?.takeIf { !it.isJsonNull }?.getAsDouble() } catch (_: Exception) { null }
                                val marginType = try { jsonObject.get("margin_type")?.takeIf { !it.isJsonNull }?.getAsString() } catch (_: Exception) { null }
                                UpdateMessage.PositionUpdate(
                                    strategyId = strategyId,
                                    strategyName = strategyName,
                                    symbol = symbol,
                                    accountId = accountId,
                                    positionSize = positionSize,
                                    entryPrice = entryPrice,
                                    unrealizedPnl = unrealizedPnl,
                                    positionSide = positionSide,
                                    currentPrice = currentPrice,
                                    leverage = leverage,
                                    liquidationPrice = liquidationPrice,
                                    initialMargin = initialMargin,
                                    marginType = marginType
                                )
                            }
                            "strategy_update" -> {
                                val data = jsonObject.getAsJsonObject("data")
                                val strategyId = data.get("strategyId")?.asString ?: ""
                                val status = data.get("status")?.asString ?: ""
                                AppLogger.d("WebSocketManager", "Creating StrategyUpdate: strategyId=$strategyId, status=$status")
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
                isConnecting = false
                isConnected = false
                val rawMessage = when {
                    response?.code == 404 -> "WebSocket endpoint not found (404). Backend WebSocket server not implemented yet."
                    response != null -> "WebSocket connection failed: ${response.code} ${response.message}"
                    else -> t.message ?: "Connection failed"
                }
                AppLogger.e("WebSocketManager", rawMessage)
                // User-facing message: avoid raw "failed to connect to /IP from /IP (port)" on transient failures; we reconnect automatically
                val userMessage = if (response?.code == 404) rawMessage
                else "Connection lost. Reconnecting…"
                if (response?.code != 404) {
                    scope.launch {
                        _updates.tryEmit(UpdateMessage.Error(userMessage))
                    }
                }
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
        isConnecting = false
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
    /** Real-time position/PnL update from backend (mark price stream or position event). strategyId may be synthetic "manual_$symbol" when backend sends null. */
    data class PositionUpdate(
        val strategyId: String,
        val strategyName: String? = null,
        val symbol: String,
        val accountId: String,
        val positionSize: Double,
        val entryPrice: Double?,
        val unrealizedPnl: Double?,
        val positionSide: String?,
        val currentPrice: Double?,
        val leverage: Int? = null,
        val liquidationPrice: Double? = null,
        val initialMargin: Double? = null,
        val marginType: String? = null
    ) : UpdateMessage()
    data class Error(val message: String) : UpdateMessage()
}

