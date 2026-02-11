package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.remote.dto.MarketAnalysisResponse
import com.binancebot.mobile.domain.repository.MarketAnalyzerRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class MarketAnalyzerViewModel @Inject constructor(
    private val repository: MarketAnalyzerRepository
) : ViewModel() {
    
    private val _analysis = MutableStateFlow<MarketAnalysisResponse?>(null)
    val analysis: StateFlow<MarketAnalysisResponse?> = _analysis.asStateFlow()
    
    private val _uiState = MutableStateFlow<MarketAnalyzerUiState>(MarketAnalyzerUiState.Idle)
    val uiState: StateFlow<MarketAnalyzerUiState> = _uiState.asStateFlow()
    
    fun analyzeMarket(
        symbol: String,
        interval: String = "5m",
        lookbackPeriod: Int = 150,
        emaFastPeriod: Int = 20,
        emaSlowPeriod: Int = 50,
        maxEmaSpreadPct: Double = 0.005,
        rsiPeriod: Int = 14,
        swingPeriod: Int = 5
    ) {
        viewModelScope.launch {
            _uiState.value = MarketAnalyzerUiState.Loading
            repository.analyzeMarket(
                symbol = symbol,
                interval = interval,
                lookbackPeriod = lookbackPeriod,
                emaFastPeriod = emaFastPeriod,
                emaSlowPeriod = emaSlowPeriod,
                maxEmaSpreadPct = maxEmaSpreadPct,
                rsiPeriod = rsiPeriod,
                swingPeriod = swingPeriod
            )
                .onSuccess { response ->
                    _analysis.value = response
                    _uiState.value = MarketAnalyzerUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = MarketAnalyzerUiState.Error(error.message ?: "Failed to analyze market")
                }
        }
    }
}

sealed class MarketAnalyzerUiState {
    object Idle : MarketAnalyzerUiState()
    object Loading : MarketAnalyzerUiState()
    object Success : MarketAnalyzerUiState()
    data class Error(val message: String) : MarketAnalyzerUiState()
}





































