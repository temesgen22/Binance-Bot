package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.domain.repository.ReportsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ReportsViewModel @Inject constructor(
    private val reportsRepository: ReportsRepository
) : ViewModel() {
    
    private val _tradingReport = MutableStateFlow<com.binancebot.mobile.data.remote.dto.TradingReportDto?>(null)
    val tradingReport: StateFlow<com.binancebot.mobile.data.remote.dto.TradingReportDto?> = _tradingReport.asStateFlow()
    
    private val _uiState = MutableStateFlow<ReportsUiState>(ReportsUiState.Idle)
    val uiState: StateFlow<ReportsUiState> = _uiState.asStateFlow()
    
    fun loadTradingReport(
        strategyId: String? = null,
        accountId: String? = null,
        dateFrom: String? = null,
        dateTo: String? = null
    ) {
        viewModelScope.launch {
            _uiState.value = ReportsUiState.Loading
            reportsRepository.getTradingReport(
                strategyId = strategyId,
                accountId = accountId,
                startDate = dateFrom,
                endDate = dateTo
            )
                .onSuccess { report ->
                    _tradingReport.value = report
                    _uiState.value = ReportsUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = ReportsUiState.Error(error.message ?: "Failed to load trading report")
                }
        }
    }
}

sealed class ReportsUiState {
    object Idle : ReportsUiState()
    object Loading : ReportsUiState()
    object Success : ReportsUiState()
    data class Error(val message: String) : ReportsUiState()
}
