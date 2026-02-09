package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.domain.repository.LogsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class LogsViewModel @Inject constructor(
    private val logsRepository: LogsRepository
) : ViewModel() {
    
    private val _logs = MutableStateFlow<com.binancebot.mobile.data.remote.dto.LogResponse?>(null)
    val logs: StateFlow<com.binancebot.mobile.data.remote.dto.LogResponse?> = _logs.asStateFlow()
    
    private val _uiState = MutableStateFlow<LogsUiState>(LogsUiState.Idle)
    val uiState: StateFlow<LogsUiState> = _uiState.asStateFlow()
    
    fun loadLogs(
        symbol: String? = null,
        level: String? = null,
        searchText: String? = null,
        dateFrom: String? = null,
        dateTo: String? = null
    ) {
        viewModelScope.launch {
            _uiState.value = LogsUiState.Loading
            logsRepository.getLogs(
                symbol = symbol,
                level = level,
                searchText = searchText,
                dateFrom = dateFrom,
                dateTo = dateTo
            )
                .onSuccess { logResponse ->
                    _logs.value = logResponse
                    _uiState.value = LogsUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = LogsUiState.Error(error.message ?: "Failed to load logs")
                }
        }
    }
}

sealed class LogsUiState {
    object Idle : LogsUiState()
    object Loading : LogsUiState()
    object Success : LogsUiState()
    data class Error(val message: String) : LogsUiState()
}
