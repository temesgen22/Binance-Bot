package com.binancebot.mobile.presentation.screens.pricealerts

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.data.remote.dto.PriceAlertDto
import com.binancebot.mobile.presentation.viewmodel.PriceAlertsUiState
import com.binancebot.mobile.presentation.viewmodel.PriceAlertsViewModel

private fun alertTypeLabel(type: String): String = when (type) {
    "PRICE_RISES_ABOVE" -> "Rises above"
    "PRICE_DROPS_BELOW" -> "Drops below"
    "PRICE_REACHES" -> "Reaches"
    else -> type
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PriceAlertsScreen(
    navController: NavController,
    viewModel: PriceAlertsViewModel = hiltViewModel()
) {
    val alerts by viewModel.alerts.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    val filterEnabled by viewModel.filterEnabled.collectAsState()
    var deleteConfirmId by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        viewModel.loadAlerts()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Price Alerts") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {}
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { navController.navigate("price_alert_form") }
            ) {
                Icon(Icons.Default.Add, contentDescription = "Add alert")
            }
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FilterChip(
                    selected = filterEnabled == null,
                    onClick = { viewModel.setFilter(null) },
                    label = { Text("All") }
                )
                FilterChip(
                    selected = filterEnabled == true,
                    onClick = { viewModel.setFilter(true) },
                    label = { Text("Enabled") }
                )
                FilterChip(
                    selected = filterEnabled == false,
                    onClick = { viewModel.setFilter(false) },
                    label = { Text("Disabled") }
                )
            }

            when (uiState) {
                is PriceAlertsUiState.Loading -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator()
                    }
                }
                is PriceAlertsUiState.Error -> {
                    val msg = (uiState as PriceAlertsUiState.Error).message
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text(
                                text = msg,
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.error
                            )
                            TextButton(onClick = { viewModel.loadAlerts() }) {
                                Text("Retry")
                            }
                        }
                    }
                }
                else -> {
                    if (alerts.isEmpty()) {
                        Box(
                            modifier = Modifier.fillMaxSize(),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(
                                horizontalAlignment = Alignment.CenterHorizontally,
                                verticalArrangement = Arrangement.spacedBy(16.dp)
                            ) {
                                Text(
                                    text = "No price alerts",
                                    style = MaterialTheme.typography.bodyLarge,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Button(onClick = { navController.navigate("price_alert_form") }) {
                                    Text("Add alert")
                                }
                            }
                        }
                    } else {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            items(items = alerts, key = { it.id }) { alert ->
                                PriceAlertCard(
                                    alert = alert,
                                    onEdit = { navController.navigate("price_alert_form/${alert.id}") },
                                    onToggle = { viewModel.toggleEnabled(alert) },
                                    onDelete = { deleteConfirmId = alert.id }
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    deleteConfirmId?.let { id ->
        AlertDialog(
            onDismissRequest = { deleteConfirmId = null },
            title = { Text("Delete alert") },
            text = { Text("Delete this price alert?") },
            confirmButton = {
                TextButton(
                    onClick = {
                        viewModel.deleteAlert(id) {
                            deleteConfirmId = null
                        }
                    }
                ) {
                    Text("Delete", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { deleteConfirmId = null }) {
                    Text("Cancel")
                }
            }
        )
    }
}

@Composable
private fun PriceAlertCard(
    alert: PriceAlertDto,
    onEdit: () -> Unit,
    onToggle: () -> Unit,
    onDelete: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = alert.symbol,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                AssistChip(
                    onClick = { },
                    label = {
                        Text(if (alert.enabled) "Enabled" else "Disabled")
                    },
                    colors = AssistChipDefaults.assistChipColors(
                        containerColor = if (alert.enabled)
                            MaterialTheme.colorScheme.primaryContainer
                        else
                            MaterialTheme.colorScheme.surfaceVariant
                    )
                )
            }
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "${alertTypeLabel(alert.alertType)} ${alert.targetPrice}",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (alert.lastPrice != null) {
                Text(
                    text = "Last price: ${alert.lastPrice}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                TextButton(onClick = onEdit) {
                    Icon(Icons.Default.Edit, contentDescription = null, Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Edit")
                }
                TextButton(onClick = onToggle) {
                    Text(if (alert.enabled) "Disable" else "Enable")
                }
                TextButton(
                    onClick = onDelete,
                    colors = ButtonDefaults.textButtonColors(
                        contentColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Icon(Icons.Default.Delete, contentDescription = null, Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Delete")
                }
            }
        }
    }
}
