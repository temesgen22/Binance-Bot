package com.binancebot.mobile.presentation.screens.risk

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.RiskManagementViewModel
import com.binancebot.mobile.presentation.viewmodel.RiskManagementUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RiskManagementScreen(
    navController: NavController,
    viewModel: RiskManagementViewModel = hiltViewModel()
) {
    var selectedTabIndex by remember { mutableStateOf(0) }
    val portfolioRiskStatus by viewModel.portfolioRiskStatus.collectAsState()
    val riskConfig by viewModel.riskConfig.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
    LaunchedEffect(Unit) {
        viewModel.refresh()
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Risk Management") },
                actions = {
                    IconButton(onClick = { viewModel.refresh() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
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
            // Tabs
            TabRow(selectedTabIndex = selectedTabIndex) {
                Tab(
                    selected = selectedTabIndex == 0,
                    onClick = { selectedTabIndex = 0 },
                    text = { Text("Portfolio Status") }
                )
                Tab(
                    selected = selectedTabIndex == 1,
                    onClick = { selectedTabIndex = 1 },
                    text = { Text("Configuration") }
                )
            }
            
            // Tab Content
            when (selectedTabIndex) {
                0 -> PortfolioStatusTab(
                    portfolioRiskStatus = portfolioRiskStatus,
                    uiState = uiState,
                    onRetry = { viewModel.loadPortfolioRiskStatus() }
                )
                1 -> ConfigurationTab(
                    riskConfig = riskConfig,
                    onRetry = { viewModel.loadRiskConfig() }
                )
            }
        }
    }
}

@Composable
fun PortfolioStatusTab(
    portfolioRiskStatus: com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto?,
    uiState: RiskManagementUiState,
    onRetry: () -> Unit
) {
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
                onRetry = onRetry,
                modifier = Modifier.fillMaxSize()
            )
        }
        else -> {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(Spacing.ScreenPadding),
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                portfolioRiskStatus?.let { status ->
                    // Status Card (Highlighted)
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                        colors = CardDefaults.cardColors(
                            containerColor = when (status.status.lowercase()) {
                                "active" -> MaterialTheme.colorScheme.primaryContainer
                                "warning" -> MaterialTheme.colorScheme.errorContainer
                                else -> MaterialTheme.colorScheme.surfaceVariant
                            }
                        )
                    ) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(Spacing.CardPadding),
                            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "Portfolio Risk Status",
                                    style = MaterialTheme.typography.titleLarge,
                                    fontWeight = FontWeight.Bold
                                )
                                Surface(
                                    shape = MaterialTheme.shapes.small,
                                    color = MaterialTheme.colorScheme.surface
                                ) {
                                    Text(
                                        text = status.status.replaceFirstChar { it.uppercase() },
                                        modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                                        style = MaterialTheme.typography.labelMedium,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                            }
                            Divider()
                            
                            // Key Metrics Grid
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = "Total Exposure",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Text(
                                        text = status.totalExposure?.let { FormatUtils.formatCurrency(it) } ?: "N/A",
                                        style = MaterialTheme.typography.titleMedium,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = "Total PnL",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Text(
                                        text = status.totalPnL?.let { 
                                            FormatUtils.formatCurrency(it)
                                        } ?: "N/A",
                                        style = MaterialTheme.typography.titleMedium,
                                        fontWeight = FontWeight.Bold,
                                        color = status.totalPnL?.let {
                                            if (it >= 0) MaterialTheme.colorScheme.primary 
                                            else MaterialTheme.colorScheme.error
                                        } ?: MaterialTheme.colorScheme.onSurface
                                    )
                                }
                            }
                            
                            // Additional Metrics
                            status.maxDrawdown?.let {
                                MetricRow("Max Drawdown", "${String.format("%.2f", it * 100)}%")
                            }
                            // Note: activePositions and totalStrategies are not in the DTO
                            // These would need to be added to PortfolioRiskStatusDto if needed
                        }
                    }
                } ?: run {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                    ) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(Spacing.Large),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Text(
                                text = "No risk status data available",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun ConfigurationTab(
    riskConfig: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?,
    onRetry: () -> Unit
) {
    var showEditDialog by remember { mutableStateOf(false) }
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(Spacing.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
    ) {
        riskConfig?.let { config ->
            Card(
                modifier = Modifier.fillMaxWidth(),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(Spacing.CardPadding),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "Risk Configuration",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold
                        )
                        Button(
                            onClick = { showEditDialog = true }
                        ) {
                            Text("Edit")
                        }
                    }
                    Divider()
                    
                    config.maxPortfolioExposure?.let {
                        MetricRow("Max Portfolio Exposure", FormatUtils.formatCurrency(it))
                    }
                    config.maxDailyLoss?.let {
                        MetricRow("Max Daily Loss", FormatUtils.formatCurrency(it))
                    }
                    config.maxDrawdownPct?.let {
                        MetricRow("Max Drawdown", "${String.format("%.2f", it * 100)}%")
                    }
                    // Note: maxPositionSize, maxLeverage, enableStopLoss, enableTakeProfit
                    // are not in the RiskManagementConfigDto
                    // These would need to be added to the DTO if needed
                }
            }
            
            // Additional Info Card
            Card(
                modifier = Modifier.fillMaxWidth(),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant
                )
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(Spacing.CardPadding),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    Text(
                        text = "ℹ️ Risk Management Info",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "These settings help protect your portfolio by limiting exposure and potential losses. Adjust them based on your risk tolerance.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        } ?: run {
            Card(
                modifier = Modifier.fillMaxWidth(),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(Spacing.Large),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    Text(
                        text = "No risk configuration found",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = "Create a risk configuration to protect your portfolio",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Button(onClick = { showEditDialog = true }) {
                        Text("Create Configuration")
                    }
                }
            }
        }
    }
    
    // Edit Configuration Dialog
    if (showEditDialog && riskConfig != null) {
        EditRiskConfigDialog(
            config = riskConfig,
            onDismiss = { showEditDialog = false },
            onSave = { updatedConfig ->
                // TODO: Implement API call to update risk config
                // viewModel.updateRiskConfig(updatedConfig)
                showEditDialog = false
            }
        )
    }
}

@Composable
fun MetricRow(
    label: String,
    value: String,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Bold
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EditRiskConfigDialog(
    config: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto,
    onDismiss: () -> Unit,
    onSave: (com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto) -> Unit
) {
    var maxPortfolioExposure by remember { mutableStateOf(config.maxPortfolioExposure?.toString() ?: "") }
    var maxDailyLoss by remember { mutableStateOf(config.maxDailyLoss?.toString() ?: "") }
    var maxDrawdownPct by remember { mutableStateOf((config.maxDrawdownPct?.times(100))?.toString() ?: "") }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Edit Risk Configuration") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                OutlinedTextField(
                    value = maxPortfolioExposure,
                    onValueChange = { maxPortfolioExposure = it },
                    label = { Text("Max Portfolio Exposure (USD)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                OutlinedTextField(
                    value = maxDailyLoss,
                    onValueChange = { maxDailyLoss = it },
                    label = { Text("Max Daily Loss (USD)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                OutlinedTextField(
                    value = maxDrawdownPct,
                    onValueChange = { maxDrawdownPct = it },
                    label = { Text("Max Drawdown (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Text(
                    text = "Note: Changes will be saved to the server",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    // Create updated config (simplified - would need proper DTO mapping)
                    // For now, just dismiss as API integration is needed
                    onDismiss()
                }
            ) {
                Text("Save")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}
