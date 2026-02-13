package com.binancebot.mobile.presentation.viewmodel

import android.util.Log
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.domain.model.Strategy
import com.binancebot.mobile.domain.repository.StrategyRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class StrategiesViewModel @Inject constructor(
    private val strategyRepository: StrategyRepository
) : ViewModel() {
    
    private val _strategies = MutableStateFlow<List<Strategy>>(emptyList())
    val strategies: StateFlow<List<Strategy>> = _strategies.asStateFlow()
    
    private val _uiState = MutableStateFlow<StrategiesUiState>(StrategiesUiState.Idle)
    val uiState: StateFlow<StrategiesUiState> = _uiState.asStateFlow()
    
    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()
    
    private val _strategyHealth = MutableStateFlow<Map<String, com.binancebot.mobile.data.remote.dto.StrategyHealthDto>>(emptyMap())
    val strategyHealth: StateFlow<Map<String, com.binancebot.mobile.data.remote.dto.StrategyHealthDto>> = _strategyHealth.asStateFlow()
    
    private val _strategyToCopy = MutableStateFlow<StrategyPerformanceDto?>(null)
    val strategyToCopy: StateFlow<StrategyPerformanceDto?> = _strategyToCopy.asStateFlow()
    
    fun setStrategyToCopy(performance: StrategyPerformanceDto?) {
        _strategyToCopy.value = performance
    }
    
    fun clearStrategyToCopy() {
        _strategyToCopy.value = null
    }
    
    init {
        loadStrategies()
    }
    
    fun loadStrategyHealth(strategyId: String) {
        viewModelScope.launch {
            try {
                Log.d("StrategyHealth", "ViewModel: Loading health for $strategyId")
                strategyRepository.getStrategyHealth(strategyId)
                    .onSuccess { health ->
                        Log.d("StrategyHealth", "ViewModel: Health loaded successfully for $strategyId: ${health.healthStatus}")
                        _strategyHealth.value = _strategyHealth.value.toMutableMap().apply {
                            put(strategyId, health)
                        }
                    }
                    .onFailure { error ->
                        // Log error but don't crash - health check is optional
                        Log.e("StrategyHealth", "ViewModel: Failed to load health for $strategyId: ${error.message}")
                    }
            } catch (e: Exception) {
                Log.e("StrategyHealth", "ViewModel: Exception loading health for $strategyId", e)
            }
        }
    }
    
    fun loadStrategies() {
        viewModelScope.launch {
            _uiState.value = StrategiesUiState.Loading
            strategyRepository.getStrategies()
                .onSuccess { strategies ->
                    _strategies.value = strategies
                    _uiState.value = StrategiesUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = StrategiesUiState.Error(error.message ?: "Failed to load strategies")
                }
        }
    }
    
    fun refreshStrategies() {
        viewModelScope.launch {
            try {
                _isRefreshing.value = true
                strategyRepository.getStrategies()
                    .onSuccess { strategies ->
                        _strategies.value = strategies
                    }
                    .onFailure { /* Silent fail on refresh */ }
            } finally {
                _isRefreshing.value = false
            }
        }
    }
    
    private val _actionInProgress = MutableStateFlow<Set<String>>(emptySet())
    val actionInProgress: StateFlow<Set<String>> = _actionInProgress.asStateFlow()
    
    /** Trigger for the Strategies screen to refresh performance list (so Start/Stop button updates). */
    private val _refreshPerformanceTrigger = MutableStateFlow(0)
    val refreshPerformanceTrigger: StateFlow<Int> = _refreshPerformanceTrigger.asStateFlow()
    
    fun startStrategy(strategyId: String) {
        viewModelScope.launch {
            _actionInProgress.value = _actionInProgress.value + strategyId
            strategyRepository.startStrategy(strategyId)
                .onSuccess {
                    loadStrategies()
                    _refreshPerformanceTrigger.value += 1
                }
                .onFailure { error ->
                    _uiState.value = StrategiesUiState.Error(error.message ?: "Failed to start strategy")
                }
            _actionInProgress.value = _actionInProgress.value - strategyId
        }
    }
    
    fun stopStrategy(strategyId: String) {
        viewModelScope.launch {
            _actionInProgress.value = _actionInProgress.value + strategyId
            strategyRepository.stopStrategy(strategyId)
                .onSuccess {
                    loadStrategies()
                    _refreshPerformanceTrigger.value += 1
                }
                .onFailure { error ->
                    _uiState.value = StrategiesUiState.Error(error.message ?: "Failed to stop strategy")
                }
            _actionInProgress.value = _actionInProgress.value - strategyId
        }
    }
    
    fun deleteStrategy(strategyId: String) {
        viewModelScope.launch {
            strategyRepository.deleteStrategy(strategyId)
                .onSuccess {
                    loadStrategies() // Reload after deletion
                }
                .onFailure { error ->
                    _uiState.value = StrategiesUiState.Error(error.message ?: "Failed to delete strategy")
                }
        }
    }
    
    fun clearCreateSuccess() {
        _uiState.value = StrategiesUiState.Idle
    }
    
    fun createStrategy(
        name: String,
        symbol: String,
        strategyType: String,
        leverage: Int,
        riskPerTrade: Double?,
        fixedAmount: Double?,
        accountId: String,
        params: Map<String, Any> = emptyMap()
    ) {
        viewModelScope.launch {
            _uiState.value = StrategiesUiState.Loading
            val request = com.binancebot.mobile.data.remote.dto.CreateStrategyRequest(
                name = name,
                symbol = symbol,
                strategyType = strategyType,
                leverage = leverage,
                riskPerTrade = riskPerTrade,
                fixedAmount = fixedAmount,
                accountId = accountId,
                params = params
            )
            
            strategyRepository.createStrategy(request)
                .onSuccess {
                    _uiState.value = StrategiesUiState.CreateSuccess
                }
                .onFailure { error ->
                    _uiState.value = StrategiesUiState.Error(error.message ?: "Failed to create strategy")
                }
        }
    }
    
    fun updateStrategy(strategyId: String, request: com.binancebot.mobile.data.remote.dto.UpdateStrategyRequest) {
        viewModelScope.launch {
            _uiState.value = StrategiesUiState.Loading
            strategyRepository.updateStrategy(strategyId, request)
                .onSuccess {
                    _uiState.value = StrategiesUiState.Success
                    loadStrategies() // Reload to show updated strategy
                }
                .onFailure { error ->
                    _uiState.value = StrategiesUiState.Error(error.message ?: "Failed to update strategy")
                }
        }
    }
    
    fun startAllStrategies() {
        viewModelScope.launch {
            val strategiesToStart = _strategies.value.filter { !it.isRunning }
            strategiesToStart.forEach { strategy ->
                strategyRepository.startStrategy(strategy.id)
                    .onFailure { error ->
                        _uiState.value = StrategiesUiState.Error("Failed to start ${strategy.name}: ${error.message}")
                    }
            }
            loadStrategies() // Reload to get updated status
        }
    }
    
    fun stopAllStrategies() {
        viewModelScope.launch {
            val strategiesToStop = _strategies.value.filter { it.isRunning }
            strategiesToStop.forEach { strategy ->
                strategyRepository.stopStrategy(strategy.id)
                    .onFailure { error ->
                        _uiState.value = StrategiesUiState.Error("Failed to stop ${strategy.name}: ${error.message}")
                    }
            }
            loadStrategies() // Reload to get updated status
        }
    }
}

sealed class StrategiesUiState {
    object Idle : StrategiesUiState()
    object Loading : StrategiesUiState()
    object Success : StrategiesUiState()
    object CreateSuccess : StrategiesUiState()
    data class Error(val message: String) : StrategiesUiState()
}
