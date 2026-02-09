package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.remote.dto.BacktestResultDto
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class BacktestingViewModel @Inject constructor(
    // TODO: Inject BacktestingRepository when API is available
) : ViewModel() {
    
    private val _backtestHistory = MutableStateFlow<List<BacktestResultDto>>(emptyList())
    val backtestHistory: StateFlow<List<BacktestResultDto>> = _backtestHistory.asStateFlow()
    
    private val _uiState = MutableStateFlow<BacktestingUiState>(BacktestingUiState.Idle)
    val uiState: StateFlow<BacktestingUiState> = _uiState.asStateFlow()
    
    init {
        loadBacktestHistory()
    }
    
    fun loadBacktestHistory() {
        viewModelScope.launch {
            _uiState.value = BacktestingUiState.Loading
            // TODO: Implement API call when backend is available
            // For now, return empty list
            _backtestHistory.value = emptyList()
            _uiState.value = BacktestingUiState.Success
        }
    }
    
    fun runBacktest(
        strategyId: String,
        startDate: String,
        endDate: String
    ) {
        viewModelScope.launch {
            _uiState.value = BacktestingUiState.Loading
            // TODO: Implement API call when backend is available
            // For now, just show error
            _uiState.value = BacktestingUiState.Error("Backtesting API not yet implemented. Please wait for backend support.")
        }
    }
}

sealed class BacktestingUiState {
    object Idle : BacktestingUiState()
    object Loading : BacktestingUiState()
    object Success : BacktestingUiState()
    data class Error(val message: String) : BacktestingUiState()
}



