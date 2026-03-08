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

    fun apply(update: UpdateMessage.PositionUpdate) {
        val key = if (update.strategyId.isBlank()) "manual_${update.symbol}" else update.strategyId
        val data = PositionUpdateData(
            strategyId = update.strategyId,
            strategyName = update.strategyName,
            symbol = update.symbol,
            accountId = update.accountId,
            positionSize = update.positionSize,
            entryPrice = update.entryPrice,
            unrealizedPnl = update.unrealizedPnl,
            positionSide = update.positionSide,
            currentPrice = update.currentPrice,
            leverage = update.leverage,
            liquidationPrice = update.liquidationPrice,
            initialMargin = update.initialMargin,
            marginType = update.marginType
        )
        if (update.positionSize <= 0) {
            _updates.value = _updates.value + (key to data.copy(positionSize = 0.0))
        } else {
            _updates.value = _updates.value + (key to data)
        }
    }
}

data class PositionUpdateData(
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
)
