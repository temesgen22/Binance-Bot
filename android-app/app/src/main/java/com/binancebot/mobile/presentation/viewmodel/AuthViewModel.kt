package com.binancebot.mobile.presentation.viewmodel

import android.content.Context
import android.os.Build
import android.provider.Settings
import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.BuildConfig
import com.binancebot.mobile.data.remote.dto.LoginRequest
import com.binancebot.mobile.data.remote.dto.RegisterRequest
import com.binancebot.mobile.domain.repository.AuthRepository
import com.binancebot.mobile.domain.repository.NotificationRepository
import com.binancebot.mobile.util.TokenManager
import com.google.firebase.messaging.FirebaseMessaging
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import javax.inject.Inject

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val notificationRepository: NotificationRepository,
    private val tokenManager: TokenManager,
    @ApplicationContext private val context: Context
) : ViewModel() {
    
    private val _uiState = MutableStateFlow<AuthUiState>(AuthUiState.Idle)
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()
    
    fun login(username: String, password: String) {
        viewModelScope.launch {
            _uiState.value = AuthUiState.Loading
            authRepository.login(LoginRequest(username, password))
                .onSuccess { response ->
                    tokenManager.saveTokens(response.accessToken, response.refreshToken)
                    
                    // Register FCM token after successful login
                    registerFcmToken()
                    
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
                            
                            // Register FCM token after successful login
                            registerFcmToken()
                            
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
    
    /**
     * Register FCM token with backend after login.
     * This ensures push notifications work even if onNewToken was called before login.
     */
    private fun registerFcmToken() {
        viewModelScope.launch {
            try {
                // Get FCM token
                val fcmToken = FirebaseMessaging.getInstance().token.await()
                
                // Get device info
                val deviceId = Settings.Secure.getString(
                    context.contentResolver,
                    Settings.Secure.ANDROID_ID
                )
                val deviceName = "${Build.MANUFACTURER} ${Build.MODEL}"
                val appVersion = BuildConfig.VERSION_NAME
                
                // Register with backend
                notificationRepository.registerFcmToken(
                    fcmToken = fcmToken,
                    deviceId = deviceId,
                    deviceName = deviceName,
                    appVersion = appVersion
                )
                    .onSuccess {
                        Log.d("AuthViewModel", "FCM token registered successfully after login")
                    }
                    .onFailure { e ->
                        Log.e("AuthViewModel", "Failed to register FCM token after login", e)
                    }
            } catch (e: Exception) {
                Log.e("AuthViewModel", "Failed to get FCM token", e)
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
