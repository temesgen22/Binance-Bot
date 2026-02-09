package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.domain.model.Strategy
import com.binancebot.mobile.domain.repository.StrategyRepository
import com.binancebot.mobile.domain.repository.StrategyPerformanceRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class StrategyDetailsViewModel @Inject constructor(
    private val strategyRepository: StrategyRepository,
    private val performanceRepository: StrategyPerformanceRepository
) : ViewModel() {
    
    private val _strategy = MutableStateFlow<Strategy?>(null)
    val strategy: StateFlow<Strategy?> = _strategy.asStateFlow()
    
    private val _stats = MutableStateFlow<com.binancebot.mobile.data.remote.dto.StrategyStatsDto?>(null)
    val stats: StateFlow<com.binancebot.mobile.data.remote.dto.StrategyStatsDto?> = _stats.asStateFlow()
    
    private val _performance = MutableStateFlow<com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto?>(null)
    val performance: StateFlow<com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto?> = _performance.asStateFlow()
    
    private val _uiState = MutableStateFlow<StrategyDetailsUiState>(StrategyDetailsUiState.Idle)
    val uiState: StateFlow<StrategyDetailsUiState> = _uiState.asStateFlow()
    
    fun loadStrategyDetails(strategyId: String) {
        viewModelScope.launch {
            _uiState.value = StrategyDetailsUiState.Loading
            
            // Load strategy, stats, and performance in parallel
            val strategyResult = strategyRepository.getStrategy(strategyId)
            val statsResult = strategyRepository.getStrategyStats(strategyId)
            val performanceResult = performanceRepository.getStrategyPerformanceById(strategyId)
            
            when {
                strategyResult.isSuccess -> {
                    _strategy.value = strategyResult.getOrNull()
                    _stats.value = statsResult.getOrNull()
                    _performance.value = performanceResult.getOrNull()
                    _uiState.value = StrategyDetailsUiState.Success
                }
                else -> {
                    _uiState.value = StrategyDetailsUiState.Error(
                        strategyResult.exceptionOrNull()?.message ?: "Failed to load strategy"
                    )
                }
            }
        }
    }
    
    fun refresh(strategyId: String) {
        loadStrategyDetails(strategyId)
    }
    
    fun startStrategy(strategyId: String) {
        viewModelScope.launch {
            strategyRepository.startStrategy(strategyId)
                .onSuccess {
                    loadStrategyDetails(strategyId) // Reload to get updated status
                }
                .onFailure { error ->
                    _uiState.value = StrategyDetailsUiState.Error(error.message ?: "Failed to start strategy")
                }
        }
    }
    
    fun stopStrategy(strategyId: String) {
        viewModelScope.launch {
            strategyRepository.stopStrategy(strategyId)
                .onSuccess {
                    loadStrategyDetails(strategyId) // Reload to get updated status
                }
                .onFailure { error ->
                    _uiState.value = StrategyDetailsUiState.Error(error.message ?: "Failed to stop strategy")
                }
        }
    }
}

sealed class StrategyDetailsUiState {
    object Idle : StrategyDetailsUiState()
    object Loading : StrategyDetailsUiState()
    object Success : StrategyDetailsUiState()
    data class Error(val message: String) : StrategyDetailsUiState()
}




