package com.binancebot.mobile.presentation.screens.notifications

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.domain.model.Notification
import com.binancebot.mobile.presentation.components.NotificationCard
import com.binancebot.mobile.presentation.viewmodel.NotificationHistoryViewModel
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NotificationHistoryScreen(
    navController: NavController,
    viewModel: NotificationHistoryViewModel = hiltViewModel()
) {
    val notifications by viewModel.notifications.collectAsState()
    val unreadCount by viewModel.unreadCount.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    val selectedFilter by viewModel.selectedFilter.collectAsState()
    
    var showMarkAllReadDialog by remember { mutableStateOf(false) }
    
    LaunchedEffect(Unit) {
        viewModel.loadNotifications()
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Notifications") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    if (unreadCount > 0) {
                        TextButton(
                            onClick = { showMarkAllReadDialog = true }
                        ) {
                            Text("Mark All Read")
                        }
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            // Filter chips
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FilterChip(
                    selected = selectedFilter == null,
                    onClick = { viewModel.loadNotifications(null) },
                    label = { Text("All") }
                )
                FilterChip(
                    selected = selectedFilter == "trade",
                    onClick = { viewModel.loadNotifications("trade") },
                    label = { Text("Trades") }
                )
                FilterChip(
                    selected = selectedFilter == "alert",
                    onClick = { viewModel.loadNotifications("alert") },
                    label = { Text("Alerts") }
                )
                FilterChip(
                    selected = selectedFilter == "strategy",
                    onClick = { viewModel.loadNotifications("strategy") },
                    label = { Text("Strategy") }
                )
                FilterChip(
                    selected = selectedFilter == "system",
                    onClick = { viewModel.loadNotifications("system") },
                    label = { Text("System") }
                )
            }
            
            // Notifications list
            when (uiState) {
                is com.binancebot.mobile.presentation.viewmodel.NotificationHistoryUiState.Loading -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator()
                    }
                }
                is com.binancebot.mobile.presentation.viewmodel.NotificationHistoryUiState.Error -> {
                    val errorState = uiState as com.binancebot.mobile.presentation.viewmodel.NotificationHistoryUiState.Error
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text(
                                text = errorState.message,
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.error
                            )
                            TextButton(onClick = { viewModel.refresh() }) {
                                Text("Retry")
                            }
                        }
                    }
                }
                else -> {
                    if (notifications.isEmpty()) {
                        Box(
                            modifier = Modifier.fillMaxSize(),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = "No notifications",
                                style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    } else {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            items(
                                items = notifications,
                                key = { it.id }
                            ) { notification ->
                                NotificationCard(
                                    notification = notification,
                                    onRead = { viewModel.markAsRead(notification.id) },
                                    onDelete = { viewModel.deleteNotification(notification.id) },
                                    onClick = {
                                        // Navigate based on actionUrl
                                        notification.actionUrl?.let { url ->
                                            navController.navigate(url)
                                        }
                                        if (!notification.read) {
                                            viewModel.markAsRead(notification.id)
                                        }
                                    }
                                )
                            }
                        }
                    }
                }
            }
        }
    }
    
    // Mark all as read dialog
    if (showMarkAllReadDialog) {
        AlertDialog(
            onDismissRequest = { showMarkAllReadDialog = false },
            title = { Text("Mark All as Read") },
            text = { Text("Mark all notifications as read?") },
            confirmButton = {
                TextButton(
                    onClick = {
                        viewModel.markAllAsRead()
                        showMarkAllReadDialog = false
                    }
                ) {
                    Text("Mark All")
                }
            },
            dismissButton = {
                TextButton(onClick = { showMarkAllReadDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }
}



