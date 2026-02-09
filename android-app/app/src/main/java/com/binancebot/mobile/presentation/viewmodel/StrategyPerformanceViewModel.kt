package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceListDto
import com.binancebot.mobile.domain.repository.StrategyPerformanceRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class StrategyPerformanceViewModel @Inject constructor(
    private val repository: StrategyPerformanceRepository
) : ViewModel() {
    
    private val _performanceList = MutableStateFlow<StrategyPerformanceListDto?>(null)
    val performanceList: StateFlow<StrategyPerformanceListDto?> = _performanceList.asStateFlow()
    
    private val _uiState = MutableStateFlow<StrategyPerformanceUiState>(StrategyPerformanceUiState.Idle)
    val uiState: StateFlow<StrategyPerformanceUiState> = _uiState.asStateFlow()
    
    init {
        loadPerformance()
    }
    
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
}

sealed class StrategyPerformanceUiState {
    object Idle : StrategyPerformanceUiState()
    object Loading : StrategyPerformanceUiState()
    object Success : StrategyPerformanceUiState()
    data class Error(val message: String) : StrategyPerformanceUiState()
}



























