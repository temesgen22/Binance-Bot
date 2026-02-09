package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.remote.dto.ChangePasswordRequest
import com.binancebot.mobile.data.remote.dto.UpdateProfileRequest
import com.binancebot.mobile.domain.repository.AuthRepository
import com.binancebot.mobile.util.PreferencesManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val preferencesManager: PreferencesManager
) : ViewModel() {
    
    private val _currentUser = MutableStateFlow<com.binancebot.mobile.data.remote.dto.UserResponse?>(null)
    val currentUser: StateFlow<com.binancebot.mobile.data.remote.dto.UserResponse?> = _currentUser.asStateFlow()
    
    private val _uiState = MutableStateFlow<SettingsUiState>(SettingsUiState.Idle)
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()
    
    // Preferences
    val themeMode = preferencesManager.themeMode
    val notificationsEnabled = preferencesManager.notificationsEnabled
    val language = preferencesManager.language
    
    init {
        loadCurrentUser()
    }
    
    fun loadCurrentUser() {
        viewModelScope.launch {
            _uiState.value = SettingsUiState.Loading
            authRepository.getCurrentUser()
                .onSuccess { user ->
                    _currentUser.value = user
                    _uiState.value = SettingsUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = SettingsUiState.Error(error.message ?: "Failed to load user profile")
                }
        }
    }
    
    fun updateProfile(username: String, email: String) {
        viewModelScope.launch {
            _uiState.value = SettingsUiState.Loading
            authRepository.updateProfile(UpdateProfileRequest(username, email))
                .onSuccess { user ->
                    _currentUser.value = user
                    _uiState.value = SettingsUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = SettingsUiState.Error(error.message ?: "Failed to update profile")
                }
        }
    }
    
    fun changePassword(oldPassword: String, newPassword: String) {
        viewModelScope.launch {
            _uiState.value = SettingsUiState.Loading
            authRepository.changePassword(ChangePasswordRequest(oldPassword, newPassword))
                .onSuccess {
                    _uiState.value = SettingsUiState.Success
                }
                .onFailure { error ->
                    _uiState.value = SettingsUiState.Error(error.message ?: "Failed to change password")
                }
        }
    }
    
    suspend fun setThemeMode(mode: String) {
        preferencesManager.setThemeMode(mode)
    }
    
    suspend fun setNotificationsEnabled(enabled: Boolean) {
        preferencesManager.setNotificationsEnabled(enabled)
    }
    
    suspend fun setLanguage(lang: String) {
        preferencesManager.setLanguage(lang)
    }
}

sealed class SettingsUiState {
    object Idle : SettingsUiState()
    object Loading : SettingsUiState()
    object Success : SettingsUiState()
    data class Error(val message: String) : SettingsUiState()
}



