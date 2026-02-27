package com.binancebot.mobile.presentation.viewmodel

import com.binancebot.mobile.util.AppLogger
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.domain.model.Strategy
import com.binancebot.mobile.domain.repository.StrategyRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
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
    
    /** Flow of health for a single strategy; use in list items to avoid recomposing all cards when any health updates. */
    fun strategyHealthFor(strategyId: String): Flow<com.binancebot.mobile.data.remote.dto.StrategyHealthDto?> =
        strategyHealth.map { it[strategyId] }.distinctUntilChanged()
    
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
                AppLogger.d("StrategyHealth", "ViewModel: Loading health for $strategyId")
                strategyRepository.getStrategyHealth(strategyId)
                    .onSuccess { health ->
                        AppLogger.d("StrategyHealth", "ViewModel: Health loaded successfully for $strategyId: ${health.healthStatus}")
                        _strategyHealth.value = _strategyHealth.value.toMutableMap().apply {
                            put(strategyId, health)
                        }
                    }
                    .onFailure { error ->
                        // Log error but don't crash - health check is optional
                        AppLogger.e("StrategyHealth", "ViewModel: Failed to load health for $strategyId: ${error.message}")
                    }
            } catch (e: Exception) {
                AppLogger.e("StrategyHealth", "ViewModel: Exception loading health for $strategyId", e)
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

    /** Emits (strategyId, status) on start/stop success so only that strategy card can refresh. */
    private val _strategyStatusUpdate = MutableSharedFlow<Pair<String, String>>(extraBufferCapacity = 1)
    val strategyStatusUpdate: SharedFlow<Pair<String, String>> = _strategyStatusUpdate.asSharedFlow()

    /** Emits strategyId when a strategy is deleted so the performance list can remove that card. */
    private val _strategyRemoved = MutableSharedFlow<String>(extraBufferCapacity = 1)
    val strategyRemoved: SharedFlow<String> = _strategyRemoved.asSharedFlow()

    fun startStrategy(strategyId: String) {
        viewModelScope.launch {
            _actionInProgress.value = _actionInProgress.value + strategyId
            strategyRepository.startStrategy(strategyId)
                .onSuccess {
                    _strategyStatusUpdate.emit(strategyId to "running")
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
                    _strategyStatusUpdate.emit(strategyId to "stopped")
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
                    loadStrategies()
                    _strategyRemoved.emit(strategyId)
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
            loadStrategies() // Fresh list so we know which to start
            val strategiesToStart = _strategies.value.filter { !it.isRunning }
            strategiesToStart.forEach { strategy ->
                strategyRepository.startStrategy(strategy.id)
                    .onSuccess { _strategyStatusUpdate.emit(strategy.id to "running") }
                    .onFailure { error ->
                        _uiState.value = StrategiesUiState.Error("Failed to start ${strategy.name}: ${error.message}")
                    }
            }
        }
    }

    fun stopAllStrategies() {
        viewModelScope.launch {
            loadStrategies() // Fresh list so we know which to stop
            val strategiesToStop = _strategies.value.filter { it.isRunning }
            strategiesToStop.forEach { strategy ->
                strategyRepository.stopStrategy(strategy.id)
                    .onSuccess { _strategyStatusUpdate.emit(strategy.id to "stopped") }
                    .onFailure { error ->
                        _uiState.value = StrategiesUiState.Error("Failed to stop ${strategy.name}: ${error.message}")
                    }
            }
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
