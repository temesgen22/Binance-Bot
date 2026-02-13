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
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
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
    
    private val _activity = MutableStateFlow<List<com.binancebot.mobile.data.remote.dto.StrategyActivityDto>>(emptyList())
    val activity: StateFlow<List<com.binancebot.mobile.data.remote.dto.StrategyActivityDto>> = _activity.asStateFlow()
    
    private val _uiState = MutableStateFlow<StrategyDetailsUiState>(StrategyDetailsUiState.Idle)
    val uiState: StateFlow<StrategyDetailsUiState> = _uiState.asStateFlow()
    
    private val _actionInProgress = MutableStateFlow<String?>(null)
    val actionInProgress: StateFlow<String?> = _actionInProgress.asStateFlow()
    
    fun loadStrategyDetails(strategyId: String) {
        viewModelScope.launch {
            _uiState.value = StrategyDetailsUiState.Loading
            
            // Load strategy, performance, and activity in parallel
            // Note: stats endpoint doesn't exist (returns 404), so we use performance data instead
            val strategyDeferred = async { strategyRepository.getStrategy(strategyId) }
            val performanceDeferred = async { performanceRepository.getStrategyPerformanceById(strategyId) }
            val activityDeferred = async { strategyRepository.getStrategyActivity(strategyId, limit = 50) }
            // Try to load stats, but don't fail if it doesn't exist (404 is expected)
            val statsDeferred = async { 
                try {
                    strategyRepository.getStrategyStats(strategyId)
                } catch (e: Exception) {
                    Result.failure(e)
                }
            }
            
            val strategyResult = strategyDeferred.await()
            val performanceResult = performanceDeferred.await()
            val activityResult = activityDeferred.await()
            val statsResult = statsDeferred.await()
            
            when {
                strategyResult.isSuccess -> {
                    _strategy.value = strategyResult.getOrNull()
                    _stats.value = statsResult.getOrNull() // Will be null if endpoint doesn't exist
                    _performance.value = performanceResult.getOrNull()
                    _activity.value = activityResult.getOrNull() ?: emptyList()
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
            _actionInProgress.value = strategyId
            strategyRepository.startStrategy(strategyId)
                .onSuccess {
                    loadStrategyDetails(strategyId) // Reload to get updated status
                }
                .onFailure { error ->
                    _uiState.value = StrategyDetailsUiState.Error(error.message ?: "Failed to start strategy")
                }
            _actionInProgress.value = null
        }
    }
    
    fun stopStrategy(strategyId: String) {
        viewModelScope.launch {
            _actionInProgress.value = strategyId
            strategyRepository.stopStrategy(strategyId)
                .onSuccess {
                    loadStrategyDetails(strategyId) // Reload to get updated status
                }
                .onFailure { error ->
                    _uiState.value = StrategyDetailsUiState.Error(error.message ?: "Failed to stop strategy")
                }
            _actionInProgress.value = null
        }
    }
}

sealed class StrategyDetailsUiState {
    object Idle : StrategyDetailsUiState()
    object Loading : StrategyDetailsUiState()
    object Success : StrategyDetailsUiState()
    data class Error(val message: String) : StrategyDetailsUiState()
}




