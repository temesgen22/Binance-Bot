package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.domain.repository.RiskManagementRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class RiskManagementViewModel @Inject constructor(
    private val riskManagementRepository: RiskManagementRepository
) : ViewModel() {
    
    private val _portfolioRiskStatus = MutableStateFlow<com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto?>(null)
    val portfolioRiskStatus: StateFlow<com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto?> = _portfolioRiskStatus.asStateFlow()
    
    private val _portfolioMetrics = MutableStateFlow<com.binancebot.mobile.data.remote.dto.PortfolioRiskMetricsDto?>(null)
    val portfolioMetrics: StateFlow<com.binancebot.mobile.data.remote.dto.PortfolioRiskMetricsDto?> = _portfolioMetrics.asStateFlow()
    
    private val _strategyMetrics = MutableStateFlow<List<com.binancebot.mobile.data.remote.dto.StrategyRiskMetricsDto>>(emptyList())
    val strategyMetrics: StateFlow<List<com.binancebot.mobile.data.remote.dto.StrategyRiskMetricsDto>> = _strategyMetrics.asStateFlow()
    
    private val _enforcementHistory = MutableStateFlow<com.binancebot.mobile.data.remote.dto.EnforcementHistoryDto?>(null)
    val enforcementHistory: StateFlow<com.binancebot.mobile.data.remote.dto.EnforcementHistoryDto?> = _enforcementHistory.asStateFlow()
    
    private val _dailyReport = MutableStateFlow<com.binancebot.mobile.data.remote.dto.RiskReportDto?>(null)
    val dailyReport: StateFlow<com.binancebot.mobile.data.remote.dto.RiskReportDto?> = _dailyReport.asStateFlow()
    
    private val _weeklyReport = MutableStateFlow<com.binancebot.mobile.data.remote.dto.RiskReportDto?>(null)
    val weeklyReport: StateFlow<com.binancebot.mobile.data.remote.dto.RiskReportDto?> = _weeklyReport.asStateFlow()
    
    private val _riskConfig = MutableStateFlow<com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?>(null)
    val riskConfig: StateFlow<com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?> = _riskConfig.asStateFlow()
    
    private val _uiState = MutableStateFlow<RiskManagementUiState>(RiskManagementUiState.Idle)
    val uiState: StateFlow<RiskManagementUiState> = _uiState.asStateFlow()
    
    fun loadPortfolioRiskStatus(accountId: String? = null) {
        viewModelScope.launch {
            _uiState.value = RiskManagementUiState.Loading
            riskManagementRepository.getPortfolioRiskStatus(accountId)
                .onSuccess { status ->
                    _portfolioRiskStatus.value = status
                    _uiState.value = RiskManagementUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = RiskManagementUiState.Error(error.message ?: "Failed to load risk status")
                }
        }
    }
    
    fun loadRiskConfig(accountId: String? = null) {
        viewModelScope.launch {
            riskManagementRepository.getRiskConfig(accountId)
                .onSuccess { config ->
                    _riskConfig.value = config
                }
                .onFailure { /* Silent fail */ }
        }
    }
    
    fun refresh(accountId: String? = null) {
        loadPortfolioRiskStatus(accountId)
        loadPortfolioMetrics(accountId)
        loadRiskConfig(accountId)
    }
    
    fun loadPortfolioMetrics(accountId: String? = null) {
        viewModelScope.launch {
            riskManagementRepository.getPortfolioRiskMetrics(accountId)
                .onSuccess { metrics ->
                    _portfolioMetrics.value = metrics
                }
                .onFailure { /* Silent fail */ }
        }
    }
    
    fun loadAllStrategyMetrics(accountId: String? = null) {
        viewModelScope.launch {
            _uiState.value = RiskManagementUiState.Loading
            riskManagementRepository.getAllStrategyRiskMetrics(accountId)
                .onSuccess { metrics ->
                    _strategyMetrics.value = metrics
                    _uiState.value = RiskManagementUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = RiskManagementUiState.Error(error.message ?: "Failed to load strategy metrics")
                }
        }
    }
    
    fun loadEnforcementHistory(
        accountId: String? = null,
        eventType: String? = null,
        limit: Int = 50,
        offset: Int = 0
    ) {
        viewModelScope.launch {
            _uiState.value = RiskManagementUiState.Loading
            riskManagementRepository.getEnforcementHistory(accountId, eventType, limit, offset)
                .onSuccess { history ->
                    _enforcementHistory.value = history
                    _uiState.value = RiskManagementUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = RiskManagementUiState.Error(error.message ?: "Failed to load enforcement history")
                }
        }
    }
    
    fun loadDailyReport(accountId: String? = null) {
        viewModelScope.launch {
            _uiState.value = RiskManagementUiState.Loading
            riskManagementRepository.getDailyRiskReport(accountId)
                .onSuccess { report ->
                    _dailyReport.value = report
                    _uiState.value = RiskManagementUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = RiskManagementUiState.Error(error.message ?: "Failed to load daily report")
                }
        }
    }
    
    fun loadWeeklyReport(accountId: String? = null) {
        viewModelScope.launch {
            _uiState.value = RiskManagementUiState.Loading
            riskManagementRepository.getWeeklyRiskReport(accountId)
                .onSuccess { report ->
                    _weeklyReport.value = report
                    _uiState.value = RiskManagementUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = RiskManagementUiState.Error(error.message ?: "Failed to load weekly report")
                }
        }
    }
    
    fun updateRiskConfig(accountId: String? = null, config: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto) {
        viewModelScope.launch {
            _uiState.value = RiskManagementUiState.Loading
            riskManagementRepository.updateRiskConfig(accountId, config)
                .onSuccess { updatedConfig ->
                    _riskConfig.value = updatedConfig
                    _uiState.value = RiskManagementUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = RiskManagementUiState.Error(error.message ?: "Failed to update risk configuration")
                }
        }
    }
    
    fun createRiskConfig(accountId: String? = null, config: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto) {
        viewModelScope.launch {
            _uiState.value = RiskManagementUiState.Loading
            riskManagementRepository.createRiskConfig(accountId, config)
                .onSuccess { createdConfig ->
                    _riskConfig.value = createdConfig
                    _uiState.value = RiskManagementUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = RiskManagementUiState.Error(error.message ?: "Failed to create risk configuration")
                }
        }
    }
}

sealed class RiskManagementUiState {
    object Idle : RiskManagementUiState()
    object Loading : RiskManagementUiState()
    object Success : RiskManagementUiState()
    data class Error(val message: String) : RiskManagementUiState()
}
