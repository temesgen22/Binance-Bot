package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.remote.dto.AutoTuningConfigDto
import com.binancebot.mobile.domain.model.Strategy
import com.binancebot.mobile.domain.repository.AutoTuningRepository
import com.binancebot.mobile.domain.repository.StrategyRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class AutoTuningViewModel @Inject constructor(
    private val autoTuningRepository: AutoTuningRepository,
    private val strategyRepository: StrategyRepository
) : ViewModel() {
    
    private val _strategies = MutableStateFlow<List<Strategy>>(emptyList())
    val strategies: StateFlow<List<Strategy>> = _strategies.asStateFlow()
    
    private val _uiState = MutableStateFlow<AutoTuningUiState>(AutoTuningUiState.Idle)
    val uiState: StateFlow<AutoTuningUiState> = _uiState.asStateFlow()
    
    fun loadStrategies() {
        viewModelScope.launch {
            _uiState.value = AutoTuningUiState.Loading
            strategyRepository.getStrategies()
                .onSuccess { strategiesList ->
                    _strategies.value = strategiesList
                    _uiState.value = AutoTuningUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = AutoTuningUiState.Error(
                        error.message ?: "Failed to load strategies"
                    )
                }
        }
    }
    
    fun enableAutoTuning(
        strategyId: String,
        config: AutoTuningConfigDto = AutoTuningConfigDto() // Default config
    ) {
        viewModelScope.launch {
            _uiState.value = AutoTuningUiState.Loading
            autoTuningRepository.enableAutoTuning(strategyId, config)
                .onSuccess {
                    // Refresh strategies to get updated auto-tuning status
                    loadStrategies()
                    _uiState.value = AutoTuningUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = AutoTuningUiState.Error(
                        error.message ?: "Failed to enable auto-tuning"
                    )
                }
        }
    }
    
    fun disableAutoTuning(strategyId: String) {
        viewModelScope.launch {
            _uiState.value = AutoTuningUiState.Loading
            autoTuningRepository.disableAutoTuning(strategyId)
                .onSuccess {
                    // Refresh strategies to get updated auto-tuning status
                    loadStrategies()
                    _uiState.value = AutoTuningUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = AutoTuningUiState.Error(
                        error.message ?: "Failed to disable auto-tuning"
                    )
                }
        }
    }
    
    fun tuneNow(strategyId: String) {
        viewModelScope.launch {
            _uiState.value = AutoTuningUiState.Loading
            autoTuningRepository.tuneNow(strategyId)
                .onSuccess {
                    _uiState.value = AutoTuningUiState.Success
                    // Optionally refresh strategies after tuning
                    loadStrategies()
                }
                .onFailure { error ->
                    _uiState.value = AutoTuningUiState.Error(
                        error.message ?: "Failed to trigger tuning"
                    )
                }
        }
    }
}

sealed class AutoTuningUiState {
    object Idle : AutoTuningUiState()
    object Loading : AutoTuningUiState()
    object Success : AutoTuningUiState()
    data class Error(val message: String) : AutoTuningUiState()
}



