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
        loadRiskConfig(accountId)
    }
}

sealed class RiskManagementUiState {
    object Idle : RiskManagementUiState()
    object Loading : RiskManagementUiState()
    object Success : RiskManagementUiState()
    data class Error(val message: String) : RiskManagementUiState()
}
