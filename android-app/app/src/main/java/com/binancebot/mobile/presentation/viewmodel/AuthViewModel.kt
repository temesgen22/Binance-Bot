package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.remote.dto.LoginRequest
import com.binancebot.mobile.data.remote.dto.RegisterRequest
import com.binancebot.mobile.domain.repository.AuthRepository
import com.binancebot.mobile.util.TokenManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val tokenManager: TokenManager
) : ViewModel() {
    
    private val _uiState = MutableStateFlow<AuthUiState>(AuthUiState.Idle)
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()
    
    fun login(username: String, password: String) {
        viewModelScope.launch {
            _uiState.value = AuthUiState.Loading
            authRepository.login(LoginRequest(username, password))
                .onSuccess { response ->
                    tokenManager.saveTokens(response.accessToken, response.refreshToken)
                    _uiState.value = AuthUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = AuthUiState.Error(error.message ?: "Login failed")
                }
        }
    }
    
    fun register(request: RegisterRequest) {
        viewModelScope.launch {
            _uiState.value = AuthUiState.Loading
            authRepository.register(request)
                .onSuccess { userResponse ->
                    // After successful registration, auto-login to get tokens
                    authRepository.login(LoginRequest(request.username, request.password))
                        .onSuccess { loginResponse ->
                            tokenManager.saveTokens(loginResponse.accessToken, loginResponse.refreshToken)
                            _uiState.value = AuthUiState.Success
                        }
                        .onFailure { error ->
                            // Registration succeeded but auto-login failed
                            _uiState.value = AuthUiState.Error("Registration successful. Please login manually.")
                        }
                }
                .onFailure { error ->
                    _uiState.value = AuthUiState.Error(error.message ?: "Registration failed")
                }
        }
    }
    
    fun logout() {
        tokenManager.clearTokens()
        _uiState.value = AuthUiState.Idle
    }
}

sealed class AuthUiState {
    object Idle : AuthUiState()
    object Loading : AuthUiState()
    object Success : AuthUiState()
    data class Error(val message: String) : AuthUiState()
}
