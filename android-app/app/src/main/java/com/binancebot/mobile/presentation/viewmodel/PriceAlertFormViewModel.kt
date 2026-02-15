package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.remote.dto.CreatePriceAlertRequest
import com.binancebot.mobile.data.remote.dto.PriceAlertDto
import com.binancebot.mobile.data.remote.dto.UpdatePriceAlertRequest
import com.binancebot.mobile.domain.repository.PriceAlertsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed class PriceAlertFormUiState {
    object Loading : PriceAlertFormUiState()
    data class Loaded(val alert: PriceAlertDto?) : PriceAlertFormUiState()
    object Saving : PriceAlertFormUiState()
    object SaveSuccess : PriceAlertFormUiState()
    data class Error(val message: String) : PriceAlertFormUiState()
}

@HiltViewModel
class PriceAlertFormViewModel @Inject constructor(
    private val repository: PriceAlertsRepository,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    val alertId: String? = savedStateHandle.get<String>("alertId")

    private val _uiState = MutableStateFlow<PriceAlertFormUiState>(PriceAlertFormUiState.Loading)
    val uiState: StateFlow<PriceAlertFormUiState> = _uiState.asStateFlow()

    private val _symbol = MutableStateFlow("")
    val symbol: StateFlow<String> = _symbol.asStateFlow()
    private val _alertType = MutableStateFlow("PRICE_RISES_ABOVE")
    val alertType: StateFlow<String> = _alertType.asStateFlow()
    private val _targetPrice = MutableStateFlow("")
    val targetPrice: StateFlow<String> = _targetPrice.asStateFlow()
    private val _triggerOnce = MutableStateFlow(true)
    val triggerOnce: StateFlow<Boolean> = _triggerOnce.asStateFlow()

    init {
        if (alertId != null) {
            loadAlert(alertId!!)
        } else {
            _uiState.value = PriceAlertFormUiState.Loaded(null)
        }
    }

    private fun loadAlert(id: String) {
        viewModelScope.launch {
            _uiState.value = PriceAlertFormUiState.Loading
            repository.getPriceAlert(id)
                .onSuccess { alert ->
                    _symbol.value = alert.symbol
                    _alertType.value = alert.alertType
                    _targetPrice.value = alert.targetPrice.toString()
                    _triggerOnce.value = alert.triggerOnce
                    _uiState.value = PriceAlertFormUiState.Loaded(alert)
                }
                .onFailure {
                    _uiState.value = PriceAlertFormUiState.Error(it.message ?: "Failed to load alert")
                }
        }
    }

    fun setSymbol(s: String) { _symbol.value = s }
    fun setAlertType(s: String) { _alertType.value = s }
    fun setTargetPrice(s: String) { _targetPrice.value = s }
    fun setTriggerOnce(b: Boolean) { _triggerOnce.value = b }

    fun save(onSuccess: () -> Unit, onError: (String) -> Unit) {
        val sym = _symbol.value.trim().uppercase()
        val priceStr = _targetPrice.value.trim()
        val price = priceStr.toDoubleOrNull()
        if (sym.isBlank()) {
            onError("Symbol is required")
            return
        }
        if (price == null || price <= 0) {
            onError("Target price must be a positive number")
            return
        }
        viewModelScope.launch {
            _uiState.value = PriceAlertFormUiState.Saving
            if (alertId != null) {
                repository.updatePriceAlert(
                    alertId,
                    UpdatePriceAlertRequest(
                        symbol = sym,
                        alertType = _alertType.value,
                        targetPrice = price,
                        triggerOnce = _triggerOnce.value
                    )
                )
            } else {
                repository.createPriceAlert(
                    CreatePriceAlertRequest(
                        symbol = sym,
                        alertType = _alertType.value,
                        targetPrice = price,
                        triggerOnce = _triggerOnce.value
                    )
                )
            }
                .onSuccess {
                    _uiState.value = PriceAlertFormUiState.SaveSuccess
                    onSuccess()
                }
                .onFailure {
                    _uiState.value = PriceAlertFormUiState.Loaded(null)
                    onError(it.message ?: "Save failed")
                }
        }
    }
}
