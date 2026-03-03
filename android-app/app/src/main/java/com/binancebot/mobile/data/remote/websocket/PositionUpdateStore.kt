package com.binancebot.mobile.data.remote.websocket

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * In-memory store of latest position updates per strategy (from WebSocket /ws/positions).
 * ViewModels merge this with API data so the UI shows real-time PnL/price without refetch.
 */
@Singleton
class PositionUpdateStore @Inject constructor() {
    private val _updates = MutableStateFlow<Map<String, PositionUpdateData>>(emptyMap())
    val updates: StateFlow<Map<String, PositionUpdateData>> = _updates.asStateFlow()

    fun apply(update: WebSocketManager.PositionUpdate) {
        if (update.strategyId.isBlank()) return
        val data = PositionUpdateData(
            strategyId = update.strategyId,
            symbol = update.symbol,
            accountId = update.accountId,
            positionSize = update.positionSize,
            entryPrice = update.entryPrice,
            unrealizedPnl = update.unrealizedPnl,
            positionSide = update.positionSide,
            currentPrice = update.currentPrice
        )
        if (update.positionSize <= 0) {
            _updates.value = _updates.value - update.strategyId
        } else {
            _updates.value = _updates.value + (update.strategyId to data)
        }
    }
}

data class PositionUpdateData(
    val strategyId: String,
    val symbol: String,
    val accountId: String,
    val positionSize: Double,
    val entryPrice: Double?,
    val unrealizedPnl: Double?,
    val positionSide: String?,
    val currentPrice: Double?
)
