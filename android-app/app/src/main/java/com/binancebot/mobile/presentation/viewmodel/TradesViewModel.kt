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
    
    /** Merge REST positions with WebSocket store: WS adds/updates/removes by strategyId (or synthetic "manual_$symbol"). One position per symbol; WS wins when both have same symbol. */
    private fun mergePositionsWithWs(
        restPositions: List<Position>,
        wsUpdates: Map<String, PositionUpdateData>
    ): List<Position> {
        val wsOpen = wsUpdates.values
            .filter { it.positionSize > 0 }
            .map { it.toPosition() }
        val wsSymbols = wsOpen.map { it.symbol }.toSet()
        // Keep REST position only if no WS update for that symbol, and (if has strategyId) no WS update for that strategyId or WS says closed
        val restOpen = restPositions.filter { p ->
            if (p.symbol in wsSymbols) return@filter false
            val sid = p.strategyId
            sid == null || sid !in wsUpdates || (wsUpdates[sid]?.positionSize ?: 0.0) <= 0.0
        }
        return restOpen + wsOpen
    }
    
    // Available symbols and strategies
    private val _availableSymbols = MutableStateFlow<List<String>>(emptyList())
    val availableSymbols: StateFlow<List<String>> = _availableSymbols.asStateFlow()
    
    private val _pnlLoading = MutableStateFlow(false)
    val pnlLoading: StateFlow<Boolean> = _pnlLoading.asStateFlow()
    
    private val _pnlError = MutableStateFlow<String?>(null)
    val pnlError: StateFlow<String?> = _pnlError.asStateFlow()
    
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
            dateTo = params.dateTo
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
    strategyId = if (strategyId.startsWith("manual_")) null else strategyId,
    strategyName = strategyName,
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
