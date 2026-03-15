package com.binancebot.mobile.domain.repository

import androidx.paging.PagingData
import com.binancebot.mobile.domain.model.Trade
import com.binancebot.mobile.domain.model.SymbolPnL
import kotlinx.coroutines.flow.Flow

/**
 * Repository interface for Trade operations.
 * ✅ Uses Paging 3 for efficient pagination.
 */
interface TradeRepository {
    fun getTrades(
        strategyId: String? = null,
        symbol: String? = null,
        side: String? = null,
        dateFrom: String? = null,
        dateTo: String? = null,
        accountId: String? = null
    ): Flow<PagingData<Trade>>
    fun getTradesByStrategy(strategyId: String): Flow<List<Trade>>
    suspend fun getPnLOverview(
        accountId: String? = null,
        startDate: String? = null,
        endDate: String? = null
    ): Result<List<SymbolPnL>>
    suspend fun getSymbols(): Result<List<String>>

    /** Manually close a strategy-owned position; backend records exit_reason=MANUAL. */
    suspend fun manualClosePosition(
        strategyId: String,
        symbol: String? = null,
        positionSide: String? = null
    ): Result<Unit>
    
    // ========== Manual Trading ==========
    
    /** Open a manual position with optional TP/SL */
    suspend fun openManualPosition(
        symbol: String,
        side: String,
        usdtAmount: Double,
        accountId: String = "default",
        leverage: Int = 10,
        marginType: String? = "CROSSED",
        takeProfitPct: Double? = null,
        stopLossPct: Double? = null,
        tpPrice: Double? = null,
        slPrice: Double? = null,
        trailingStopEnabled: Boolean = false,
        trailingStopCallbackRate: Double? = null,
        notes: String? = null
    ): Result<ManualOpenResult>
    
    /** Close a manual position (full or partial) */
    suspend fun closeManualPosition(
        positionId: String,
        quantity: Double? = null
    ): Result<ManualCloseResult>
    
    /** Get list of manual positions */
    suspend fun getManualPositions(
        status: String? = null,
        accountId: String? = null,
        symbol: String? = null
    ): Result<List<ManualPositionInfo>>
}

/** Result of opening a manual position */
data class ManualOpenResult(
    val positionId: String,
    val entryOrderId: Long,
    val symbol: String,
    val side: String,
    val quantity: Double,
    val entryPrice: Double,
    val leverage: Int,
    val tpOrderId: Long?,
    val tpPrice: Double?,
    val slOrderId: Long?,
    val slPrice: Double?,
    val trailingStopEnabled: Boolean
)

/** Result of closing a manual position */
data class ManualCloseResult(
    val positionId: String,
    val exitOrderId: Long,
    val symbol: String,
    val side: String,
    val closedQuantity: Double,
    val remainingQuantity: Double,
    val exitPrice: Double,
    val realizedPnl: Double,
    val feePaid: Double
)

/** Manual position info for display */
data class ManualPositionInfo(
    val id: String,
    val symbol: String,
    val side: String,
    val quantity: Double,
    val remainingQuantity: Double?,
    val entryPrice: Double,
    val leverage: Int,
    val status: String,
    val tpPrice: Double?,
    val slPrice: Double?,
    val currentPrice: Double?,
    val unrealizedPnl: Double?,
    val realizedPnl: Double?,
    val createdAt: String
)








