package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.remote.dto.*
import com.binancebot.mobile.domain.repository.WalkForwardRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import javax.inject.Inject

@HiltViewModel
class WalkForwardViewModel @Inject constructor(
    private val walkForwardRepository: WalkForwardRepository
) : ViewModel() {
    
    private val _currentTaskId = MutableStateFlow<String?>(null)
    val currentTaskId: StateFlow<String?> = _currentTaskId.asStateFlow()
    
    private val _progress = MutableStateFlow<WalkForwardProgressDto?>(null)
    val progress: StateFlow<WalkForwardProgressDto?> = _progress.asStateFlow()
    
    private val _result = MutableStateFlow<WalkForwardResultDto?>(null)
    val result: StateFlow<WalkForwardResultDto?> = _result.asStateFlow()
    
    private val _history = MutableStateFlow<List<WalkForwardHistoryItemDto>>(emptyList())
    val history: StateFlow<List<WalkForwardHistoryItemDto>> = _history.asStateFlow()
    
    private val _uiState = MutableStateFlow<WalkForwardUiState>(WalkForwardUiState.Idle)
    val uiState: StateFlow<WalkForwardUiState> = _uiState.asStateFlow()
    
    private var progressPollingJob: Job? = null
    
    init {
        loadHistory()
    }
    
    fun loadHistory() {
        viewModelScope.launch {
            walkForwardRepository.getWalkForwardHistory()
                .onSuccess { historyList ->
                    _history.value = historyList
                }
                .onFailure { /* Silent fail */ }
        }
    }
    
    fun startWalkForwardAnalysis(
        symbol: String,
        strategyType: String,
        startTime: String,
        endTime: String,
        trainingPeriodDays: Int = 30,
        testPeriodDays: Int = 7,
        stepSizeDays: Int = 7,
        windowType: String = "rolling",
        leverage: Int = 5,
        riskPerTrade: Double = 0.01,
        fixedAmount: Double? = null,
        initialBalance: Double = 1000.0,
        params: Map<String, Any> = emptyMap(),
        optimizeParams: Map<String, List<Any>>? = null,
        optimizationMetric: String = "robust_score",
        optimizationMethod: String = "grid_search"
    ) {
        viewModelScope.launch {
            _uiState.value = WalkForwardUiState.Loading
            _currentTaskId.value = null
            _progress.value = null
            _result.value = null
            
            // Convert date strings to ISO 8601 format if needed
            val startTimeIso = convertToIso8601(startTime)
            val endTimeIso = convertToIso8601(endTime)
            
            val request = WalkForwardRequestDto(
                symbol = symbol,
                strategyType = strategyType,
                name = null,
                startTime = startTimeIso,
                endTime = endTimeIso,
                trainingPeriodDays = trainingPeriodDays,
                testPeriodDays = testPeriodDays,
                stepSizeDays = stepSizeDays,
                windowType = windowType,
                optimizeParams = optimizeParams,
                leverage = leverage,
                riskPerTrade = riskPerTrade,
                fixedAmount = fixedAmount,
                initialBalance = initialBalance,
                params = params,
                optimizationMetric = optimizationMetric,
                optimizationMethod = optimizationMethod
            )
            
            walkForwardRepository.startWalkForwardAnalysis(request)
                .onSuccess { response ->
                    _currentTaskId.value = response.taskId
                    _uiState.value = WalkForwardUiState.Running
                    startProgressPolling(response.taskId)
                }
                .onFailure { error ->
                    _uiState.value = WalkForwardUiState.Error(
                        error.message ?: "Failed to start walk-forward analysis"
                    )
                }
        }
    }
    
    private fun startProgressPolling(taskId: String) {
        progressPollingJob?.cancel()
        progressPollingJob = viewModelScope.launch {
            while (true) {
                delay(2000) // Poll every 2 seconds
                
                walkForwardRepository.getWalkForwardProgress(taskId)
                    .onSuccess { progress ->
                        _progress.value = progress
                        
                        when (progress.status.lowercase()) {
                            "completed" -> {
                                // Fetch final result
                                walkForwardRepository.getWalkForwardResult(taskId)
                                    .onSuccess { result ->
                                        _result.value = result
                                        _uiState.value = WalkForwardUiState.Success
                                        loadHistory() // Refresh history
                                    }
                                    .onFailure { error ->
                                        _uiState.value = WalkForwardUiState.Error(
                                            error.message ?: "Failed to get result"
                                        )
                                    }
                                return@launch
                            }
                            "failed" -> {
                                _uiState.value = WalkForwardUiState.Error(
                                    progress.message ?: "Analysis failed"
                                )
                                return@launch
                            }
                            "running" -> {
                                _uiState.value = WalkForwardUiState.Running
                            }
                        }
                    }
                    .onFailure { error ->
                        // Continue polling even if one request fails
                        // Only stop if we get a clear error
                    }
            }
        }
    }
    
    fun stopProgressPolling() {
        progressPollingJob?.cancel()
        progressPollingJob = null
    }
    
    fun clearCurrentResult() {
        stopProgressPolling()
        _currentTaskId.value = null
        _progress.value = null
        _result.value = null
        _uiState.value = WalkForwardUiState.Idle
    }
    
    fun getResult(taskId: String) {
        viewModelScope.launch {
            _uiState.value = WalkForwardUiState.Loading
            walkForwardRepository.getWalkForwardResult(taskId)
                .onSuccess { result ->
                    _result.value = result
                    _uiState.value = WalkForwardUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = WalkForwardUiState.Error(
                        error.message ?: "Failed to get result"
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
    
    override fun onCleared() {
        super.onCleared()
        stopProgressPolling()
    }
}

sealed class WalkForwardUiState {
    object Idle : WalkForwardUiState()
    object Loading : WalkForwardUiState()
    object Running : WalkForwardUiState()
    object Success : WalkForwardUiState()
    data class Error(val message: String) : WalkForwardUiState()
}
