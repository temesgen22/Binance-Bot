package com.binancebot.mobile.presentation.screens.risk

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.util.UUID
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.viewmodel.RiskManagementViewModel
import com.binancebot.mobile.presentation.viewmodel.RiskManagementUiState

// Enforcement History Tab
@Composable
fun EnforcementHistoryTab(
    enforcementHistory: com.binancebot.mobile.data.remote.dto.EnforcementHistoryDto?,
    uiState: RiskManagementUiState,
    viewModel: RiskManagementViewModel,
    accountId: String?
) {
    var eventTypeFilter by remember { mutableStateOf<String?>(null) }
    var currentPage by remember { mutableStateOf(0) }
    val pageSize = 20
    
    // Load data when account changes
    LaunchedEffect(accountId) {
        viewModel.loadEnforcementHistory(accountId, eventTypeFilter, pageSize, 0)
        currentPage = 0
    }
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(Spacing.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
    ) {
        // Filters - Fixed at top
        Card(
            modifier = Modifier.fillMaxWidth(),
            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(Spacing.CardPadding),
                verticalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                Text(
                    text = "Filters",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    FilterChip(
                        selected = eventTypeFilter == null,
                        onClick = { eventTypeFilter = null },
                        label = { Text("All") }
                    )
                    FilterChip(
                        selected = eventTypeFilter == "ORDER_BLOCKED",
                        onClick = { eventTypeFilter = if (eventTypeFilter == "ORDER_BLOCKED") null else "ORDER_BLOCKED" },
                        label = { Text("Blocked") }
                    )
                    FilterChip(
                        selected = eventTypeFilter == "CIRCUIT_BREAKER_TRIGGERED",
                        onClick = { eventTypeFilter = if (eventTypeFilter == "CIRCUIT_BREAKER_TRIGGERED") null else "CIRCUIT_BREAKER_TRIGGERED" },
                        label = { Text("Circuit Breaker") }
                    )
                }
                Button(
                    onClick = {
                        currentPage = 0
                        viewModel.loadEnforcementHistory(accountId, eventTypeFilter, pageSize, 0)
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Apply Filters")
                }
            }
        }
        
        // History List
        when (uiState) {
            is RiskManagementUiState.Loading -> {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
            is RiskManagementUiState.Error -> {
                ErrorHandler(
                    message = (uiState as RiskManagementUiState.Error).message,
                    onRetry = { viewModel.loadEnforcementHistory(accountId, eventTypeFilter, pageSize, currentPage * pageSize) },
                    modifier = Modifier.fillMaxSize()
                )
            }
            else -> {
                if (enforcementHistory?.events.isNullOrEmpty()) {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        EmptyStateCard(message = "No enforcement events found")
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(vertical = Spacing.Small),
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        items(
                            items = enforcementHistory?.events ?: emptyList(),
                            key = { it.id ?: it.createdAt ?: UUID.randomUUID().toString() }
                        ) { event ->
                            EnforcementEventCard(event = event)
                        }
                        
                        // Pagination
                        if (enforcementHistory != null && enforcementHistory.total > pageSize) {
                            item {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = Spacing.Medium),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    TextButton(
                                        onClick = {
                                            if (currentPage > 0) {
                                                currentPage--
                                                viewModel.loadEnforcementHistory(accountId, eventTypeFilter, pageSize, currentPage * pageSize)
                                            }
                                        },
                                        enabled = currentPage > 0
                                    ) {
                                        Text("Previous")
                                    }
                                    Text(
                                        text = "Page ${currentPage + 1} of ${(enforcementHistory.total + pageSize - 1) / pageSize}",
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                    TextButton(
                                        onClick = {
                                            if ((currentPage + 1) * pageSize < enforcementHistory.total) {
                                                currentPage++
                                                viewModel.loadEnforcementHistory(accountId, eventTypeFilter, pageSize, currentPage * pageSize)
                                            }
                                        },
                                        enabled = (currentPage + 1) * pageSize < enforcementHistory.total
                                    ) {
                                        Text("Next")
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun EnforcementEventCard(
    event: com.binancebot.mobile.data.remote.dto.EnforcementEventDto
) {
    val eventColor = when (event.eventLevel.lowercase()) {
        "error", "critical" -> MaterialTheme.colorScheme.error
        "warning" -> MaterialTheme.colorScheme.errorContainer
        else -> MaterialTheme.colorScheme.primary
    }
    
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Small),
            verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Surface(
                    shape = MaterialTheme.shapes.small,
                    color = eventColor.copy(alpha = 0.2f)
                ) {
                    Text(
                        text = event.eventType,
                        modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                        style = MaterialTheme.typography.labelSmall,
                        color = eventColor,
                        fontWeight = FontWeight.Bold
                    )
                }
                Text(
                    text = formatTimestamp(event.createdAt),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            
            Text(
                text = event.message,
                style = MaterialTheme.typography.bodySmall
            )
            
            if (event.strategyId != null) {
                Text(
                    text = "Strategy: ${event.strategyId}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

