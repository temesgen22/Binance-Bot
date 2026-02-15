package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.remote.dto.PriceAlertDto
import com.binancebot.mobile.data.remote.dto.UpdatePriceAlertRequest
import com.binancebot.mobile.domain.repository.PriceAlertsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed class PriceAlertsUiState {
    object Loading : PriceAlertsUiState()
    data class Success(val alerts: List<PriceAlertDto>) : PriceAlertsUiState()
    data class Error(val message: String) : PriceAlertsUiState()
}

@HiltViewModel
class PriceAlertsViewModel @Inject constructor(
    private val repository: PriceAlertsRepository
) : ViewModel() {

    private val _alerts = MutableStateFlow<List<PriceAlertDto>>(emptyList())
    val alerts: StateFlow<List<PriceAlertDto>> = _alerts.asStateFlow()

    private val _uiState = MutableStateFlow<PriceAlertsUiState>(PriceAlertsUiState.Loading)
    val uiState: StateFlow<PriceAlertsUiState> = _uiState.asStateFlow()

    private val _filterEnabled = MutableStateFlow<Boolean?>(null) // null = all, true = enabled, false = disabled
    val filterEnabled: StateFlow<Boolean?> = _filterEnabled.asStateFlow()

    fun loadAlerts(filterEnabled: Boolean? = _filterEnabled.value) {
        viewModelScope.launch {
            _uiState.value = PriceAlertsUiState.Loading
            _filterEnabled.value = filterEnabled
            repository.getPriceAlerts(enabled = filterEnabled)
                .onSuccess { list ->
                    _alerts.value = list
                    _uiState.value = PriceAlertsUiState.Success(list)
                }
                .onFailure {
                    _uiState.value = PriceAlertsUiState.Error(it.message ?: "Failed to load alerts")
                }
        }
    }

    fun setFilter(filter: Boolean?) {
        loadAlerts(filter)
    }

    fun toggleEnabled(alert: PriceAlertDto) {
        viewModelScope.launch {
            repository.updatePriceAlert(alert.id, UpdatePriceAlertRequest(enabled = !alert.enabled))
                .onSuccess { loadAlerts(_filterEnabled.value) }
                .onFailure { /* could show snackbar */ }
        }
    }

    fun deleteAlert(id: String, onSuccess: () -> Unit = {}, onError: (String) -> Unit = {}) {
        viewModelScope.launch {
            repository.deletePriceAlert(id)
                .onSuccess { loadAlerts(_filterEnabled.value); onSuccess() }
                .onFailure { onError(it.message ?: "Delete failed") }
        }
    }
}
