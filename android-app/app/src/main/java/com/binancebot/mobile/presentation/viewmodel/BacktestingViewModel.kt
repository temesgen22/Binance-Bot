package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.remote.dto.BacktestRequestDto
import com.binancebot.mobile.data.remote.dto.BacktestResultDto
import com.binancebot.mobile.domain.repository.BacktestingRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import javax.inject.Inject

@HiltViewModel
class BacktestingViewModel @Inject constructor(
    private val backtestingRepository: BacktestingRepository
) : ViewModel() {
    
    private val _backtestHistory = MutableStateFlow<List<BacktestResultDto>>(emptyList())
    val backtestHistory: StateFlow<List<BacktestResultDto>> = _backtestHistory.asStateFlow()
    
    private val _currentBacktestResult = MutableStateFlow<BacktestResultDto?>(null)
    val currentBacktestResult: StateFlow<BacktestResultDto?> = _currentBacktestResult.asStateFlow()
    
    private val _uiState = MutableStateFlow<BacktestingUiState>(BacktestingUiState.Idle)
    val uiState: StateFlow<BacktestingUiState> = _uiState.asStateFlow()
    
    fun loadBacktestHistory() {
        viewModelScope.launch {
            _uiState.value = BacktestingUiState.Loading
            // Note: Backend doesn't have a history endpoint yet
            // For now, we'll store results locally in the history list
            _uiState.value = BacktestingUiState.Success
        }
    }
    
    fun runBacktest(
        symbol: String,
        strategyType: String,
        startTime: String,
        endTime: String,
        leverage: Int = 5,
        riskPerTrade: Double = 0.01,
        fixedAmount: Double? = null,
        initialBalance: Double = 1000.0,
        params: Map<String, Any> = emptyMap(),
        includeKlines: Boolean = true
    ) {
        viewModelScope.launch {
            _uiState.value = BacktestingUiState.Loading
            _currentBacktestResult.value = null
            
            // Convert date strings to ISO 8601 format if needed
            val startTimeIso = convertToIso8601(startTime)
            val endTimeIso = convertToIso8601(endTime)
            
            val request = BacktestRequestDto(
                symbol = symbol,
                strategyType = strategyType,
                startTime = startTimeIso,
                endTime = endTimeIso,
                leverage = leverage,
                riskPerTrade = riskPerTrade,
                fixedAmount = fixedAmount,
                initialBalance = initialBalance,
                params = params,
                includeKlines = includeKlines
            )
            
            backtestingRepository.runBacktest(request)
                .onSuccess { result ->
                    _currentBacktestResult.value = result
                    // Add to history
                    _backtestHistory.value = listOf(result) + _backtestHistory.value
                    _uiState.value = BacktestingUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = BacktestingUiState.Error(
                        error.message ?: "Failed to run backtest"
                    )
                }
        }
    }
    
    private fun convertToIso8601(dateString: String): String {
        return try {
            // Try parsing as ISO 8601 first
            Instant.parse(dateString).toString()
        } catch (e: Exception) {
            try {
                // Try parsing as YYYY-MM-DD and convert to ISO 8601
                val date = java.time.LocalDate.parse(dateString)
                date.atStartOfDay(ZoneId.of("UTC")).toInstant().toString()
            } catch (e2: Exception) {
                // If all else fails, return as-is (backend will handle validation)
                dateString
            }
        }
    }
    
    fun clearCurrentResult() {
        _currentBacktestResult.value = null
    }
    
    fun setCurrentResult(result: BacktestResultDto) {
        _currentBacktestResult.value = result
    }
}

sealed class BacktestingUiState {
    object Idle : BacktestingUiState()
    object Loading : BacktestingUiState()
    object Success : BacktestingUiState()
    data class Error(val message: String) : BacktestingUiState()
}



