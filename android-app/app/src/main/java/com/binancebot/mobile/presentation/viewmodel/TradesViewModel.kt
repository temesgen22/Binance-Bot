package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.paging.PagingData
import androidx.paging.cachedIn
import com.binancebot.mobile.data.remote.websocket.PositionUpdateData
import com.binancebot.mobile.data.remote.websocket.PositionUpdateStore
import com.binancebot.mobile.domain.model.Trade
import com.binancebot.mobile.domain.model.SymbolPnL
import com.binancebot.mobile.domain.model.Position
import com.binancebot.mobile.domain.repository.TradeRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.SharingStarted
import javax.inject.Inject

@HiltViewModel
class TradesViewModel @Inject constructor(
    private val tradeRepository: TradeRepository,
    private val positionUpdateStore: PositionUpdateStore
) : ViewModel() {
    
    private val _strategyId = MutableStateFlow<String?>(null)
    private val _symbol = MutableStateFlow<String?>(null)
    private val _side = MutableStateFlow<String?>(null)
    private val _dateFrom = MutableStateFlow<String?>(null)
    private val _dateTo = MutableStateFlow<String?>(null)
    private val _accountId = MutableStateFlow<String?>(null)
    
    // PnL Overview data from REST
    private val _pnlOverview = MutableStateFlow<List<SymbolPnL>>(emptyList())
    val pnlOverview: StateFlow<List<SymbolPnL>> = _pnlOverview.asStateFlow()
    
    /** Open positions merged from REST + WebSocket so the Positions tab updates in real time. */
    val allOpenPositions: StateFlow<List<Position>> = combine(
        _pnlOverview,
        positionUpdateStore.updates
    ) { pnlList, wsUpdates ->
        mergePositionsWithWs(pnlList.flatMap { it.openPositions }, wsUpdates)
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5000),
        initialValue = emptyList()
    )
    
    // Overall statistics (use merged position count and unrealized so stats stay in sync)
    val overallStats: StateFlow<OverallStats> = combine(
        _pnlOverview,
        positionUpdateStore.updates
    ) { pnlList, wsUpdates ->
        val mergedPositions = mergePositionsWithWs(pnlList.flatMap { it.openPositions }, wsUpdates)
        var totalPnL = 0.0
        var totalRealizedPnL = 0.0
        var totalUnrealizedPnL = 0.0
        var totalTrades = 0
        var totalCompleted = 0
        var totalWinning = 0
        var totalLosing = 0
        pnlList.forEach { symbol ->
            totalPnL += symbol.totalPnL
            totalRealizedPnL += symbol.totalRealizedPnL
            totalTrades += symbol.totalTrades
            totalCompleted += symbol.completedTrades
            totalWinning += symbol.winningTrades
            totalLosing += symbol.losingTrades
        }
        // Override unrealized and active count from merged positions so they reflect WebSocket updates
        totalUnrealizedPnL = mergedPositions.sumOf { it.unrealizedPnL }
        val activePositions = mergedPositions.size
        totalPnL = totalRealizedPnL + totalUnrealizedPnL
        val winRate = if (totalCompleted > 0) {
            (totalWinning.toDouble() / totalCompleted * 100)
        } else 0.0
        OverallStats(
            totalPnL = totalPnL,
            realizedPnL = totalRealizedPnL,
            unrealizedPnL = totalUnrealizedPnL,
            totalTrades = totalTrades,
            completedTrades = totalCompleted,
            winRate = winRate,
            winningTrades = totalWinning,
            losingTrades = totalLosing,
            activePositions = activePositions
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5000),
        initialValue = OverallStats(
            totalPnL = 0.0,
            realizedPnL = 0.0,
            unrealizedPnL = 0.0,
            totalTrades = 0,
            completedTrades = 0,
            winRate = 0.0,
            winningTrades = 0,
            losingTrades = 0,
            activePositions = 0
        )
    )
    
    /** Merge REST positions with WebSocket store. WS store uses composite key "accountId|strategyId".
     * When WS sends position_update with positionSize <= 0 (closed), we exclude that position.
     * Deduplicate by (symbol, positionSide, accountId): one row per position (matches web app). */
    private fun mergePositionsWithWs(
        restPositions: List<Position>,
        wsUpdates: Map<String, PositionUpdateData>
    ): List<Position> {
        val wsOpen = wsUpdates.values
            .filter { it.positionSize > 0 }
            .map { it.toPosition() }
        fun compositeKeyFor(p: Position): String =
            positionUpdateStore.compositeKey(p.accountId ?: "default", p.strategyId ?: "", p.symbol)
        val restOpen = restPositions.filter { p ->
            val cKey = compositeKeyFor(p)
            if (cKey in wsUpdates && (wsUpdates[cKey]?.positionSize ?: 0.0) <= 0.0) return@filter false
            true
        }
        val merged = restOpen.map { TaggedPosition(it, fromRest = true) } +
            wsOpen.map { TaggedPosition(it, fromRest = false) }
        // Normalize accountId so REST (often null) and WS ("default") group together; otherwise manual positions from REST show as separate from WS and can appear as "External" (web app uses same idea)
        fun positionKey(p: Position): String = "${p.symbol}:${p.positionSide}:${p.accountId?.takeIf { it.isNotBlank() } ?: "default"}"
        val deduped = merged
            .groupBy { positionKey(it.position) }
            .values
            .map { group ->
                val rest = group.firstOrNull { it.fromRest }?.position
                // When no REST, prefer manual over strategy over external (same as web app bySymbolSide)
                val base = rest ?: group.map { it.position }.maxByOrNull { p ->
                    when {
                        p.strategyId?.startsWith("manual_") == true -> 2
                        p.strategyId?.startsWith("external_") == true -> 0
                        else -> 1
                    }
                } ?: group.first().position
                val ws = group.firstOrNull { !it.fromRest }?.position
                if (ws != null) {
                    // Overlay WS price/pnl only; keep strategyId/strategyName from REST so owner (Manual Trade / External / strategy) is correct
                    base.copy(
                        currentPrice = ws.currentPrice,
                        unrealizedPnL = ws.unrealizedPnL
                    )
                } else {
                    base
                }
            }
        // Sort like web app: by symbol, then LONG before SHORT, then by strategy_id
        return deduped.sortedWith(
            compareBy(
                { it.symbol },
                { if (it.positionSide == "LONG") 0 else 1 },
                { it.strategyId ?: "" }
            )
        )
    }

    private data class TaggedPosition(
        val position: Position,
        val fromRest: Boolean
    )
    
    // Available symbols and strategies
    private val _availableSymbols = MutableStateFlow<List<String>>(emptyList())
    val availableSymbols: StateFlow<List<String>> = _availableSymbols.asStateFlow()
    
    private val _pnlLoading = MutableStateFlow(false)
    val pnlLoading: StateFlow<Boolean> = _pnlLoading.asStateFlow()
    
    private val _pnlError = MutableStateFlow<String?>(null)
    val pnlError: StateFlow<String?> = _pnlError.asStateFlow()

    /** Composite key "accountId|strategyId" for which manual close is in progress (null when idle). */
    private val _manualCloseInProgress = MutableStateFlow<String?>(null)
    val manualCloseInProgress: StateFlow<String?> = _manualCloseInProgress.asStateFlow()

    /** Error message from last manual close attempt (cleared on next attempt or clearManualCloseError()). */
    private val _manualCloseError = MutableStateFlow<String?>(null)
    val manualCloseError: StateFlow<String?> = _manualCloseError.asStateFlow()
    
    // Recreate Flow when filters change
    // Combine filters in two groups since combine supports max 5 parameters
    val trades: Flow<PagingData<Trade>> = combine(
        combine(_strategyId, _symbol, _side) { strategyId, symbol, side ->
            Triple(strategyId, symbol, side)
        },
        combine(_dateFrom, _dateTo, _accountId) { dateFrom, dateTo, accountId ->
            Triple(dateFrom, dateTo, accountId)
        }
    ) { filters, dates ->
        // Combine all filters into a single object for flatMapLatest
        FilterParams(
            strategyId = filters.first,
            symbol = filters.second,
            side = filters.third,
            dateFrom = dates.first,
            dateTo = dates.second,
            accountId = dates.third
        )
    }.flatMapLatest { params ->
        tradeRepository.getTrades(
            strategyId = params.strategyId,
            symbol = params.symbol,
            side = params.side,
            dateFrom = params.dateFrom,
            dateTo = params.dateTo,
            accountId = params.accountId
        )
    }.cachedIn(viewModelScope)
    
    // Helper data class for filter parameters
    private data class FilterParams(
        val strategyId: String?,
        val symbol: String?,
        val side: String?,
        val dateFrom: String?,
        val dateTo: String?,
        val accountId: String?
    )
    
    fun setFilters(
        strategyId: String? = null, 
        symbol: String? = null,
        side: String? = null,
        dateFrom: String? = null,
        dateTo: String? = null,
        accountId: String? = null
    ) {
        _strategyId.value = strategyId
        _symbol.value = symbol
        _side.value = side
        _dateFrom.value = dateFrom
        _dateTo.value = dateTo
        _accountId.value = accountId
    }
    
    fun loadPnLOverview() {
        viewModelScope.launch {
            _pnlLoading.value = true
            _pnlError.value = null
            tradeRepository.getPnLOverview(
                accountId = _accountId.value,
                startDate = _dateFrom.value,
                endDate = _dateTo.value
            ).onSuccess { pnlList ->
                _pnlOverview.value = pnlList
            }.onFailure { error ->
                _pnlError.value = error.message ?: "Failed to load PnL overview"
            }
            _pnlLoading.value = false
        }
    }
    
    fun loadSymbols() {
        viewModelScope.launch {
            tradeRepository.getSymbols()
                .onSuccess { symbols ->
                    _availableSymbols.value = symbols
                }
                .onFailure { /* Silent fail */ }
        }
    }

    /** Manually close a strategy-owned position. accountId used for composite key and filtering (multi-account). */
    fun manualClosePosition(strategyId: String, symbol: String?, positionSide: String?, accountId: String? = null) {
        if (strategyId.isBlank()) return
        val acc = accountId?.takeIf { it.isNotBlank() } ?: "default"
        viewModelScope.launch {
            _manualCloseError.value = null
            val compositeInProgress = positionUpdateStore.compositeKey(acc, strategyId, symbol ?: "")
            _manualCloseInProgress.value = compositeInProgress
            tradeRepository.manualClosePosition(
                strategyId = strategyId,
                symbol = symbol?.takeIf { it.isNotBlank() },
                positionSide = positionSide?.takeIf { it.isNotBlank() }
            )
                .onSuccess {
                    _manualCloseInProgress.value = null
                    _pnlOverview.value = _pnlOverview.value.map { symbolPnL ->
                        symbolPnL.copy(
                            openPositions = symbolPnL.openPositions.filter { pos ->
                                !(pos.strategyId == strategyId && (pos.accountId ?: "default") == acc &&
                                    (symbol == null || pos.symbol == symbol))
                            }
                        )
                    }
                    val compositeKey = positionUpdateStore.compositeKey(acc, strategyId, symbol ?: "")
                    positionUpdateStore.removePosition(compositeKey)
                    loadPnLOverview()
                }
                .onFailure { e ->
                    _manualCloseInProgress.value = null
                    _manualCloseError.value = e.message ?: "Manual close failed"
                }
        }
    }

    fun clearManualCloseError() {
        _manualCloseError.value = null
    }
    
    // ========== Manual Trading ==========
    
    private val _manualTradeLoading = MutableStateFlow(false)
    val manualTradeLoading: StateFlow<Boolean> = _manualTradeLoading.asStateFlow()
    
    private val _manualTradeError = MutableStateFlow<String?>(null)
    val manualTradeError: StateFlow<String?> = _manualTradeError.asStateFlow()
    
    private val _manualTradeSuccess = MutableStateFlow<String?>(null)
    val manualTradeSuccess: StateFlow<String?> = _manualTradeSuccess.asStateFlow()
    
    /** Open a new manual position */
    fun openManualPosition(
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
    ) {
        viewModelScope.launch {
            _manualTradeLoading.value = true
            _manualTradeError.value = null
            _manualTradeSuccess.value = null
            
            tradeRepository.openManualPosition(
                symbol = symbol,
                side = side,
                usdtAmount = usdtAmount,
                accountId = accountId,
                leverage = leverage,
                marginType = marginType,
                takeProfitPct = takeProfitPct,
                stopLossPct = stopLossPct,
                tpPrice = tpPrice,
                slPrice = slPrice,
                trailingStopEnabled = trailingStopEnabled,
                trailingStopCallbackRate = trailingStopCallbackRate,
                notes = notes
            )
                .onSuccess { result ->
                    _manualTradeSuccess.value = "Position opened: ${result.symbol} ${result.side} @ $${String.format("%.2f", result.entryPrice)}"
                    loadPnLOverview() // Refresh positions
                }
                .onFailure { e ->
                    _manualTradeError.value = e.message ?: "Failed to open position"
                }
            
            _manualTradeLoading.value = false
        }
    }
    
    /** Close a manual position by ID. accountId required for composite key and filtering (multi-account). */
    fun closeManualPositionById(positionId: String, accountId: String? = null) {
        val acc = accountId?.takeIf { it.isNotBlank() } ?: "default"
        val strategyIdKey = "manual_$positionId"
        val compositeInProgress = positionUpdateStore.compositeKey(acc, strategyIdKey, "")
        viewModelScope.launch {
            _manualTradeLoading.value = true
            _manualTradeError.value = null
            _manualCloseInProgress.value = compositeInProgress

            tradeRepository.closeManualPosition(positionId)
                .onSuccess { result ->
                    _manualCloseInProgress.value = null
                    _manualTradeSuccess.value = "Position closed: PnL $${String.format("%.2f", result.realizedPnl)}"
                    _pnlOverview.value = _pnlOverview.value.map { symbolPnL ->
                        symbolPnL.copy(
                            openPositions = symbolPnL.openPositions.filter { pos ->
                                pos.strategyId != strategyIdKey || (pos.accountId ?: "default") != acc
                            }
                        )
                    }
                    val compositeKey = positionUpdateStore.compositeKey(acc, strategyIdKey, "")
                    positionUpdateStore.removePosition(compositeKey)
                    loadPnLOverview()
                }
                .onFailure { e ->
                    _manualCloseInProgress.value = null
                    _manualTradeError.value = e.message ?: "Failed to close position"
                }

            _manualTradeLoading.value = false
        }
    }

    fun clearManualTradeMessages() {
        _manualTradeError.value = null
        _manualTradeSuccess.value = null
    }

    init {
        loadSymbols()
        loadPnLOverview()
    }
}

private fun PositionUpdateData.toPosition(): Position = Position(
    symbol = symbol,
    positionSize = positionSize,
    entryPrice = entryPrice ?: 0.0,
    currentPrice = currentPrice ?: 0.0,
    positionSide = positionSide ?: "LONG",
    unrealizedPnL = unrealizedPnl ?: 0.0,
    leverage = leverage ?: 1,
    strategyId = strategyId.takeIf { it.isNotBlank() },
    strategyName = strategyName,
    accountId = accountId.takeIf { it.isNotBlank() } ?: "default",
    liquidationPrice = liquidationPrice,
    initialMargin = initialMargin,
    marginType = marginType
)

data class OverallStats(
    val totalPnL: Double,
    val realizedPnL: Double,
    val unrealizedPnL: Double,
    val totalTrades: Int,
    val completedTrades: Int,
    val winRate: Double,
    val winningTrades: Int,
    val losingTrades: Int,
    val activePositions: Int
)

sealed class TradesUiState {
    object Idle : TradesUiState()
    object Loading : TradesUiState()
    object Success : TradesUiState()
    data class Error(val message: String) : TradesUiState()
}
