package com.binancebot.mobile.data.remote.websocket

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

/**
 * In-memory store of latest position updates per (account, strategy) from WebSocket /ws/positions.
 * Uses composite key "accountId|strategyId" so the same symbol on multiple accounts (e.g. live + paper)
 * do not overwrite each other. Matches web app behavior.
 */
@Singleton
class PositionUpdateStore @Inject constructor() {
    private val _updates = MutableStateFlow<Map<String, PositionUpdateData>>(emptyMap())
    val updates: StateFlow<Map<String, PositionUpdateData>> = _updates.asStateFlow()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    /** Build composite key: accountId|strategyId (or accountId|manual_$symbol when strategyId blank). */
    fun compositeKey(accountId: String, strategyId: String, symbol: String): String {
        val acc = accountId.ifBlank { "default" }
        val strat = if (strategyId.isBlank()) "manual_$symbol" else strategyId
        return "$acc|$strat"
    }

    fun apply(update: UpdateMessage.PositionUpdate) {
        val stratKey = if (update.strategyId.isBlank()) "manual_${update.symbol}" else update.strategyId
        val key = compositeKey(update.accountId, update.strategyId, update.symbol)
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
            scope.launch {
                delay(3000)
                _updates.value = _updates.value - key
            }
        } else {
            _updates.value = _updates.value + (key to data)
        }
    }

    /**
     * Remove a position from the store (e.g., after manual close).
     * Use composite key: "${accountId}|${strategyId}" so multi-account is correct.
     */
    fun removePosition(compositeKey: String) {
        if (compositeKey.isBlank()) return
        _updates.value = _updates.value - compositeKey
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
