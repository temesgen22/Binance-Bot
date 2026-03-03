package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceListDto
import com.binancebot.mobile.data.remote.websocket.PositionUpdateStore
import com.binancebot.mobile.domain.repository.StrategyPerformanceRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class StrategyPerformanceViewModel @Inject constructor(
    private val repository: StrategyPerformanceRepository,
    private val positionUpdateStore: PositionUpdateStore
) : ViewModel() {
    
    private val _performanceList = MutableStateFlow<StrategyPerformanceListDto?>(null)
    val performanceList: StateFlow<StrategyPerformanceListDto?> = _performanceList.asStateFlow()

    /** Same as performanceList but with real-time position/PnL overlaid from WebSocket. */
    val performanceListWithLivePosition: StateFlow<StrategyPerformanceListDto?> = combine(
        _performanceList,
        positionUpdateStore.updates
    ) { list, updates ->
        if (list == null) null else list.copy(
            strategies = list.strategies.map { s ->
                val u = updates[s.strategyId]
                if (u != null) s.copy(
                    positionSize = u.positionSize,
                    totalUnrealizedPnl = u.unrealizedPnl ?: s.totalUnrealizedPnl,
                    currentPrice = u.currentPrice,
                    entryPrice = u.entryPrice ?: s.entryPrice,
                    positionSide = u.positionSide ?: s.positionSide
                ) else s
            }
        )
    }.stateIn(viewModelScope, kotlinx.coroutines.flow.SharingStarted.WhileSubscribed(5000), null)
    
    private val _uiState = MutableStateFlow<StrategyPerformanceUiState>(StrategyPerformanceUiState.Idle)
    val uiState: StateFlow<StrategyPerformanceUiState> = _uiState.asStateFlow()
    
    fun loadPerformance(
        strategyName: String? = null,
        symbol: String? = null,
        status: String? = null,
        rankBy: String? = "total_pnl",
        startDate: String? = null,
        endDate: String? = null,
        accountId: String? = null
    ) {
        viewModelScope.launch {
            _uiState.value = StrategyPerformanceUiState.Loading
            repository.getStrategyPerformance(
                strategyName = strategyName,
                symbol = symbol,
                status = status,
                rankBy = rankBy,
                startDate = startDate,
                endDate = endDate,
                accountId = accountId
            )
                .onSuccess { list ->
                    _performanceList.value = list
                    _uiState.value = StrategyPerformanceUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = StrategyPerformanceUiState.Error(error.message ?: "Failed to load performance")
                }
        }
    }

    /**
     * Optimistically update only the given strategy's status in the current list.
     * Used after start/stop so only that card recomposes without refetching the full list.
     */
    fun updateStrategyStatus(strategyId: String, status: String) {
        val current = _performanceList.value ?: return
        val newStrategies = current.strategies.map { perf ->
            if (perf.strategyId == strategyId) perf.copy(status = status) else perf
        }
        if (newStrategies != current.strategies) {
            _performanceList.value = current.copy(strategies = newStrategies)
        }
    }

    /** Remove the given strategy from the list (e.g. after delete). */
    fun removeStrategy(strategyId: String) {
        val current = _performanceList.value ?: return
        val newStrategies = current.strategies.filter { it.strategyId != strategyId }
        if (newStrategies.size != current.strategies.size) {
            _performanceList.value = current.copy(
                strategies = newStrategies,
                totalStrategies = (current.totalStrategies - 1).coerceAtLeast(0)
            )
        }
    }
}

sealed class StrategyPerformanceUiState {
    object Idle : StrategyPerformanceUiState()
    object Loading : StrategyPerformanceUiState()
    object Success : StrategyPerformanceUiState()
    data class Error(val message: String) : StrategyPerformanceUiState()
}





































