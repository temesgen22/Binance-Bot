package com.binancebot.mobile.presentation.viewmodel

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
    
    init {
        loadStrategies()
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
    
    fun startStrategy(strategyId: String) {
        viewModelScope.launch {
            strategyRepository.startStrategy(strategyId)
                .onSuccess {
                    loadStrategies() // Reload to get updated status
                }
                .onFailure { error ->
                    _uiState.value = StrategiesUiState.Error(error.message ?: "Failed to start strategy")
                }
        }
    }
    
    fun stopStrategy(strategyId: String) {
        viewModelScope.launch {
            strategyRepository.stopStrategy(strategyId)
                .onSuccess {
                    loadStrategies() // Reload to get updated status
                }
                .onFailure { error ->
                    _uiState.value = StrategiesUiState.Error(error.message ?: "Failed to stop strategy")
                }
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
    
    fun createStrategy(
        name: String,
        symbol: String,
        strategyType: String,
        leverage: Int,
        riskPerTrade: Double?,
        fixedAmount: Double?,
        accountId: String
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
                params = emptyMap() // Basic params, can be extended later
            )
            
            strategyRepository.createStrategy(request)
                .onSuccess {
                    _uiState.value = StrategiesUiState.Success
                    loadStrategies() // Reload to show new strategy
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
    data class Error(val message: String) : StrategiesUiState()
}
