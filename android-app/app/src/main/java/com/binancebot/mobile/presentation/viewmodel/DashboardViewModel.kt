package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.domain.repository.StrategyRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class DashboardViewModel @Inject constructor(
    private val strategyRepository: StrategyRepository
) : ViewModel() {
    
    private val _strategies = MutableStateFlow<List<com.binancebot.mobile.domain.model.Strategy>>(emptyList())
    val strategies: StateFlow<List<com.binancebot.mobile.domain.model.Strategy>> = _strategies.asStateFlow()
    
    private val _uiState = MutableStateFlow<DashboardUiState>(DashboardUiState.Idle)
    val uiState: StateFlow<DashboardUiState> = _uiState.asStateFlow()
    
    init {
        loadDashboardData()
    }
    
    fun loadDashboardData() {
        viewModelScope.launch {
            _uiState.value = DashboardUiState.Loading
            strategyRepository.getStrategies()
                .onSuccess { strategies ->
                    _strategies.value = strategies
                    _uiState.value = DashboardUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = DashboardUiState.Error(error.message ?: "Failed to load dashboard data")
                }
        }
    }
    
    fun refresh() {
        loadDashboardData()
    }
    
    val totalStrategies: Int
        get() = _strategies.value.size
    
    val activeStrategies: Int
        get() = _strategies.value.count { it.isRunning }
    
    val totalUnrealizedPnL: Double
        get() = _strategies.value.sumOf { it.unrealizedPnL ?: 0.0 }
}

sealed class DashboardUiState {
    object Idle : DashboardUiState()
    object Loading : DashboardUiState()
    object Success : DashboardUiState()
    data class Error(val message: String) : DashboardUiState()
}
