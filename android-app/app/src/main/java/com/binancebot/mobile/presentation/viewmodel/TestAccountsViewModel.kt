package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.remote.dto.TestAccountRequestDto
import com.binancebot.mobile.data.remote.dto.TestAccountResponseDto
import com.binancebot.mobile.domain.repository.TestAccountsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class TestAccountsViewModel @Inject constructor(
    private val repository: TestAccountsRepository
) : ViewModel() {
    
    private val _testResult = MutableStateFlow<TestAccountResponseDto?>(null)
    val testResult: StateFlow<TestAccountResponseDto?> = _testResult.asStateFlow()
    
    private val _uiState = MutableStateFlow<TestAccountsUiState>(TestAccountsUiState.Idle)
    val uiState: StateFlow<TestAccountsUiState> = _uiState.asStateFlow()
    
    fun testAccount(request: TestAccountRequestDto) {
        viewModelScope.launch {
            _uiState.value = TestAccountsUiState.Loading
            repository.testAccount(request)
                .onSuccess { result ->
                    _testResult.value = result
                    _uiState.value = TestAccountsUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = TestAccountsUiState.Error(error.message ?: "Failed to test account")
                }
        }
    }
    
    fun quickTestAccount(apiKey: String, apiSecret: String, testnet: Boolean = true) {
        viewModelScope.launch {
            _uiState.value = TestAccountsUiState.Loading
            repository.quickTestAccount(apiKey, apiSecret, testnet)
                .onSuccess { result ->
                    _testResult.value = result
                    _uiState.value = TestAccountsUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = TestAccountsUiState.Error(error.message ?: "Failed to test account")
                }
        }
    }
}

sealed class TestAccountsUiState {
    object Idle : TestAccountsUiState()
    object Loading : TestAccountsUiState()
    object Success : TestAccountsUiState()
    data class Error(val message: String) : TestAccountsUiState()
}



























