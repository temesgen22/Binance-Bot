package com.binancebot.mobile.presentation.viewmodel

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.domain.repository.DashboardRepository
import com.binancebot.mobile.domain.repository.StrategyRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class DashboardViewModel @Inject constructor(
    private val dashboardRepository: DashboardRepository,
    private val strategyRepository: StrategyRepository
) : ViewModel() {
    
    private val _strategies = MutableStateFlow<List<com.binancebot.mobile.domain.model.Strategy>>(emptyList())
    val strategies: StateFlow<List<com.binancebot.mobile.domain.model.Strategy>> = _strategies.asStateFlow()
    
    private val _dashboardOverview = MutableStateFlow<com.binancebot.mobile.data.remote.dto.DashboardOverviewDto?>(null)
    val dashboardOverview: StateFlow<com.binancebot.mobile.data.remote.dto.DashboardOverviewDto?> = _dashboardOverview.asStateFlow()
    
    private val _uiState = MutableStateFlow<DashboardUiState>(DashboardUiState.Idle)
    val uiState: StateFlow<DashboardUiState> = _uiState.asStateFlow()
    
    init {
        loadDashboardData()
    }
    
    fun loadDashboardData(startDate: String? = null, endDate: String? = null, accountId: String? = null) {
        viewModelScope.launch {
            _uiState.value = DashboardUiState.Loading
            
            var overviewLoaded = false
            var strategiesLoaded = false
            var hasError = false
            var errorMessage = ""
            
            // Load dashboard overview
            dashboardRepository.getDashboardOverview(startDate, endDate, accountId)
                .onSuccess { overview ->
                    _dashboardOverview.value = overview
                    overviewLoaded = true
                    Log.d("DashboardViewModel", "Dashboard overview loaded successfully")
                }
                .onFailure { error ->
                    // Log error but continue to load strategies
                    hasError = true
                    errorMessage = error.message ?: "Failed to load dashboard overview"
                    Log.e("DashboardViewModel", "Failed to load dashboard overview: $errorMessage", error)
                }
            
            // Load strategies for strategy list
            strategyRepository.getStrategies()
                .onSuccess { strategies ->
                    _strategies.value = strategies
                    strategiesLoaded = true
                    Log.d("DashboardViewModel", "Strategies loaded: ${strategies.size}")
                }
                .onFailure { error ->
                    hasError = true
                    if (errorMessage.isNotEmpty()) {
                        errorMessage += "; ${error.message ?: "Failed to load strategies"}"
                    } else {
                        errorMessage = error.message ?: "Failed to load strategies"
                    }
                    Log.e("DashboardViewModel", "Failed to load strategies: ${error.message}", error)
                }
            
            // Determine final state
            _uiState.value = when {
                overviewLoaded || strategiesLoaded -> DashboardUiState.Success
                hasError -> DashboardUiState.Error(errorMessage)
                else -> DashboardUiState.Error("Failed to load dashboard data")
            }
        }
    }
    
    fun refresh() {
        loadDashboardData()
    }
    
    val totalStrategies: Int
        get() = _dashboardOverview.value?.totalStrategies ?: _strategies.value.size
    
    val activeStrategies: Int
        get() = _dashboardOverview.value?.activeStrategies ?: _strategies.value.count { it.isRunning }
    
    val totalUnrealizedPnL: Double
        get() = _dashboardOverview.value?.unrealizedPnL ?: _strategies.value.sumOf { it.unrealizedPnL ?: 0.0 }
    
    val totalPnL: Double
        get() = _dashboardOverview.value?.totalPnL ?: totalUnrealizedPnL
    
    val realizedPnL: Double
        get() = _dashboardOverview.value?.realizedPnL ?: 0.0
    
    val overallWinRate: Double
        get() = _dashboardOverview.value?.overallWinRate ?: 0.0
    
    val totalTrades: Int
        get() = _dashboardOverview.value?.totalTrades ?: 0
    
    val completedTrades: Int
        get() = _dashboardOverview.value?.completedTrades ?: 0
}

sealed class DashboardUiState {
    object Idle : DashboardUiState()
    object Loading : DashboardUiState()
    object Success : DashboardUiState()
    data class Error(val message: String) : DashboardUiState()
}
