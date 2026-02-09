package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.domain.model.Account
import com.binancebot.mobile.domain.repository.AccountRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel for Account management.
 */
@HiltViewModel
class AccountViewModel @Inject constructor(
    private val repository: AccountRepository
) : ViewModel() {
    
    private val _accounts = MutableStateFlow<List<Account>>(emptyList())
    val accounts: StateFlow<List<Account>> = _accounts.asStateFlow()
    
    private val _uiState = MutableStateFlow<AccountUiState>(AccountUiState.Idle)
    val uiState: StateFlow<AccountUiState> = _uiState.asStateFlow()
    
    init {
        loadAccounts()
    }
    
    fun loadAccounts() {
        viewModelScope.launch {
            _uiState.value = AccountUiState.Loading
            repository.getAccounts()
                .onSuccess { accounts ->
                    _accounts.value = accounts
                    _uiState.value = AccountUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = AccountUiState.Error(error.message ?: "Failed to load accounts")
                }
        }
    }
    
    fun createAccount(
        accountName: String,
        apiKey: String,
        apiSecret: String,
        testnet: Boolean
    ) {
        viewModelScope.launch {
            _uiState.value = AccountUiState.Loading
            val request = com.binancebot.mobile.data.remote.dto.CreateAccountRequest(
                accountName = accountName,
                apiKey = apiKey,
                apiSecret = apiSecret,
                testnet = testnet
            )
            
            repository.createAccount(request)
                .onSuccess {
                    _uiState.value = AccountUiState.Success
                    loadAccounts() // Reload to show new account
                }
                .onFailure { error ->
                    _uiState.value = AccountUiState.Error(error.message ?: "Failed to create account")
                }
        }
    }
}

sealed class AccountUiState {
    object Idle : AccountUiState()
    object Loading : AccountUiState()
    object Success : AccountUiState()
    data class Error(val message: String) : AccountUiState()
}






























