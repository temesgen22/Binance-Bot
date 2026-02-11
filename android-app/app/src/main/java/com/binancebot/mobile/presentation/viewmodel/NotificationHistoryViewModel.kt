package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.binancebot.mobile.data.local.dao.NotificationDao
import com.binancebot.mobile.data.local.entities.NotificationEntity
import com.binancebot.mobile.domain.model.Notification
import com.binancebot.mobile.domain.repository.NotificationRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class NotificationHistoryViewModel @Inject constructor(
    private val notificationRepository: NotificationRepository,
    private val notificationDao: NotificationDao
) : ViewModel() {
    
    private val _notifications = MutableStateFlow<List<Notification>>(emptyList())
    val notifications: StateFlow<List<Notification>> = _notifications.asStateFlow()
    
    private val _unreadCount = MutableStateFlow(0)
    val unreadCount: StateFlow<Int> = _unreadCount.asStateFlow()
    
    private val _uiState = MutableStateFlow<NotificationHistoryUiState>(NotificationHistoryUiState.Idle)
    val uiState: StateFlow<NotificationHistoryUiState> = _uiState.asStateFlow()
    
    private val _selectedFilter = MutableStateFlow<String?>(null) // null = all, "trade", "alert", "strategy", "system"
    val selectedFilter: StateFlow<String?> = _selectedFilter.asStateFlow()
    
    init {
        loadNotifications()
        loadUnreadCount()
    }
    
    fun loadNotifications(filter: String? = null) {
        viewModelScope.launch {
            _uiState.value = NotificationHistoryUiState.Loading
            _selectedFilter.value = filter
            
            try {
                // Load from local database first
                val flow = if (filter != null) {
                    notificationDao.getNotificationsByType(filter)
                } else {
                    notificationDao.getAllNotifications()
                }
                
                // Collect from flow in a separate coroutine
                val flowJob = launch {
                    flow.map { entities ->
                        entities.map { it.toDomain() }
                    }.collect { notifications ->
                        _notifications.value = notifications
                        if (_uiState.value is NotificationHistoryUiState.Loading) {
                            _uiState.value = NotificationHistoryUiState.Success
                        }
                    }
                }
                
                // Also sync with backend
                launch {
                    notificationRepository.getNotificationHistory(
                        limit = 100,
                        offset = 0,
                        category = null,
                        type = filter
                    ).onSuccess { (remoteNotifications, unreadCount) ->
                        _unreadCount.value = unreadCount
                        // Local database is already updated by repository
                        // Flow will automatically update _notifications
                    }.onFailure {
                        // Continue with local data
                    }
                }
            } catch (e: Exception) {
                _uiState.value = NotificationHistoryUiState.Error(e.message ?: "Failed to load notifications")
            }
        }
    }
    
    fun loadUnreadCount() {
        viewModelScope.launch {
            notificationDao.getUnreadCount().collect { count ->
                _unreadCount.value = count
            }
        }
    }
    
    fun markAsRead(notificationId: String) {
        viewModelScope.launch {
            notificationRepository.markNotificationAsRead(notificationId)
                .onSuccess {
                    loadUnreadCount()
                }
        }
    }
    
    fun markAllAsRead() {
        viewModelScope.launch {
            notificationDao.markAllAsRead()
            loadUnreadCount()
        }
    }
    
    fun deleteNotification(notificationId: String) {
        viewModelScope.launch {
            notificationRepository.deleteNotification(notificationId)
                .onSuccess {
                    // Reload notifications
                    loadNotifications(_selectedFilter.value)
                }
        }
    }
    
    fun refresh() {
        loadNotifications(_selectedFilter.value)
        loadUnreadCount()
    }
}

sealed class NotificationHistoryUiState {
    object Idle : NotificationHistoryUiState()
    object Loading : NotificationHistoryUiState()
    object Success : NotificationHistoryUiState()
    data class Error(val message: String) : NotificationHistoryUiState()
}


