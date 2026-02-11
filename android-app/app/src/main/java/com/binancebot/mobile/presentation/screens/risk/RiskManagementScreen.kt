package com.binancebot.mobile.presentation.screens.risk

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.util.UUID
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import kotlinx.coroutines.launch
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
    var autoRefresh by remember { mutableStateOf(false) }
    var selectedAccountId by remember { mutableStateOf<String?>(null) }
    
    val portfolioRiskStatus by viewModel.portfolioRiskStatus.collectAsState()
    val portfolioMetrics by viewModel.portfolioMetrics.collectAsState()
    val strategyMetrics by viewModel.strategyMetrics.collectAsState()
    val enforcementHistory by viewModel.enforcementHistory.collectAsState()
    val dailyReport by viewModel.dailyReport.collectAsState()
    val weeklyReport by viewModel.weeklyReport.collectAsState()
    val riskConfig by viewModel.riskConfig.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
    // Force recomposition when status changes
    val currentStatus = portfolioRiskStatus?.status
    
    // Auto-refresh
    LaunchedEffect(autoRefresh, selectedAccountId) {
        if (autoRefresh) {
            while (autoRefresh) {
                kotlinx.coroutines.delay(30000) // 30 seconds
                if (!autoRefresh) break
                // Force refresh status to get latest risk_status
                viewModel.loadPortfolioRiskStatus(selectedAccountId)
                viewModel.loadPortfolioMetrics(selectedAccountId)
                viewModel.loadRiskConfig(selectedAccountId)
                viewModel.loadAllStrategyMetrics(selectedAccountId)
            }
        }
    }
    
    LaunchedEffect(Unit) {
        viewModel.refresh(selectedAccountId)
    }
    
    // Refresh status when Status tab is selected or account changes
    LaunchedEffect(selectedTabIndex, selectedAccountId) {
        if (selectedTabIndex == 0) {
            // Status tab selected - refresh status data
            viewModel.loadPortfolioRiskStatus(selectedAccountId)
            viewModel.loadPortfolioMetrics(selectedAccountId)
            viewModel.loadRiskConfig(selectedAccountId)
        }
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Risk Management") },
                actions = {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(Spacing.Tiny)
                        ) {
                            Text(
                                text = "Auto-refresh",
                                style = MaterialTheme.typography.labelSmall
                            )
                            Switch(
                                checked = autoRefresh,
                                onCheckedChange = { autoRefresh = it },
                                modifier = Modifier.size(40.dp, 24.dp)
                            )
                        }
                        IconButton(onClick = { viewModel.refresh(selectedAccountId) }) {
                            Icon(Icons.Filled.Refresh, contentDescription = "Refresh")
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
            // Account Selector
            AccountSelector(
                selectedAccountId = selectedAccountId,
                onAccountSelected = { accountId ->
                    selectedAccountId = accountId
                    viewModel.refresh(accountId)
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = Spacing.ScreenPadding, vertical = Spacing.Small)
            )
            
            // Tabs
            ScrollableTabRow(selectedTabIndex = selectedTabIndex) {
                Tab(
                    selected = selectedTabIndex == 0,
                    onClick = { 
                        selectedTabIndex = 0
                        viewModel.loadPortfolioRiskStatus(selectedAccountId)
                        viewModel.loadPortfolioMetrics(selectedAccountId)
                        viewModel.loadRiskConfig(selectedAccountId)
                    },
                    text = { Text("Status") }
                )
                Tab(
                    selected = selectedTabIndex == 1,
                    onClick = { 
                        selectedTabIndex = 1
                        viewModel.loadPortfolioMetrics(selectedAccountId)
                    },
                    text = { Text("Portfolio Metrics") }
                )
                Tab(
                    selected = selectedTabIndex == 2,
                    onClick = { 
                        selectedTabIndex = 2
                        viewModel.loadAllStrategyMetrics(selectedAccountId)
                    },
                    text = { Text("Strategy Metrics") }
                )
                Tab(
                    selected = selectedTabIndex == 3,
                    onClick = { 
                        selectedTabIndex = 3
                        viewModel.loadEnforcementHistory(selectedAccountId)
                    },
                    text = { Text("Enforcement") }
                )
                Tab(
                    selected = selectedTabIndex == 4,
                    onClick = { selectedTabIndex = 4 },
                    text = { Text("Reports") }
                )
                Tab(
                    selected = selectedTabIndex == 5,
                    onClick = { selectedTabIndex = 5 },
                    text = { Text("Configuration") }
                )
            }
            
            // Tab Content
            when (selectedTabIndex) {
                0 -> PortfolioStatusTab(
                    portfolioRiskStatus = portfolioRiskStatus,
                    portfolioMetrics = portfolioMetrics,
                    uiState = uiState,
                    onRetry = { viewModel.loadPortfolioRiskStatus(selectedAccountId) },
                    riskConfig = riskConfig,
                    viewModel = viewModel,
                    accountId = selectedAccountId
                )
                1 -> PortfolioMetricsTab(
                    portfolioMetrics = portfolioMetrics,
                    uiState = uiState,
                    onRetry = { viewModel.loadPortfolioMetrics(selectedAccountId) },
                    viewModel = viewModel,
                    accountId = selectedAccountId
                )
                2 -> StrategyMetricsTab(
                    strategyMetrics = strategyMetrics,
                    uiState = uiState,
                    viewModel = viewModel,
                    accountId = selectedAccountId
                )
                3 -> EnforcementHistoryTab(
                    enforcementHistory = enforcementHistory,
                    uiState = uiState,
                    viewModel = viewModel,
                    accountId = selectedAccountId
                )
                4 -> ReportsTab(
                    dailyReport = dailyReport,
                    weeklyReport = weeklyReport,
                    uiState = uiState,
                    viewModel = viewModel,
                    accountId = selectedAccountId
                )
                5 -> ConfigurationTab(
                    riskConfig = riskConfig,
                    onRetry = { viewModel.loadRiskConfig(selectedAccountId) },
                    viewModel = viewModel,
                    accountId = selectedAccountId
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AccountSelector(
    selectedAccountId: String?,
    onAccountSelected: (String?) -> Unit,
    modifier: Modifier = Modifier
) {
    val accountViewModel: com.binancebot.mobile.presentation.viewmodel.AccountViewModel = androidx.hilt.navigation.compose.hiltViewModel()
    val accounts by accountViewModel.accounts.collectAsState()
    var showAccountDropdown by remember { mutableStateOf(false) }
    
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Small),
            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            Text(
                text = "Account:",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold
            )
            
            ExposedDropdownMenuBox(
                expanded = showAccountDropdown,
                onExpandedChange = { showAccountDropdown = !showAccountDropdown }
            ) {
                OutlinedTextField(
                    value = when {
                        selectedAccountId == null -> "All Accounts"
                        selectedAccountId == "default" -> "Default"
                        else -> accounts.find { it.accountId == selectedAccountId }?.let { 
                            "${it.name ?: it.accountId}${if (it.testnet) " (Testnet)" else ""}"
                        } ?: selectedAccountId
                    },
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Select Account") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = showAccountDropdown) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor(),
                    singleLine = true
                )
                ExposedDropdownMenu(
                    expanded = showAccountDropdown,
                    onDismissRequest = { showAccountDropdown = false }
                ) {
                    DropdownMenuItem(
                        text = { Text("All Accounts") },
                        onClick = {
                            onAccountSelected(null)
                            showAccountDropdown = false
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Default") },
                        onClick = {
                            onAccountSelected("default")
                            showAccountDropdown = false
                        }
                    )
                    accounts.forEach { account ->
                        DropdownMenuItem(
                            text = { 
                                Text("${account.name ?: account.accountId}${if (account.testnet) " (Testnet)" else ""}")
                            },
                            onClick = {
                                onAccountSelected(account.accountId)
                                showAccountDropdown = false
                            }
                        )
                    }
                }
            }
        }
    }
}

// Portfolio Status Tab (Enhanced)
@Composable
fun PortfolioStatusTab(
    portfolioRiskStatus: com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto?,
    portfolioMetrics: com.binancebot.mobile.data.remote.dto.PortfolioRiskMetricsDto?,
    uiState: RiskManagementUiState,
    onRetry: () -> Unit,
    riskConfig: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto? = null,
    viewModel: RiskManagementViewModel? = null,
    accountId: String? = null
) {
    // Load data when account changes or when tab is first shown
    LaunchedEffect(accountId) {
        viewModel?.loadPortfolioRiskStatus(accountId)
        viewModel?.loadPortfolioMetrics(accountId)
        viewModel?.loadRiskConfig(accountId)
    }
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
                    // Status Card with Account and Timestamp
                    StatusCard(status = status)
                    
                    // Progress Bars (matching web app)
                    ProgressBarsCard(status = status, riskConfig = riskConfig)
                    
                    // Key Metrics Grid (matching web app - 6 key metrics)
                    MetricsGridCard(status = status, portfolioMetrics = portfolioMetrics)
                    
                    // Warnings & Circuit Breakers
                    if (!status.warnings.isNullOrEmpty() || !status.activeCircuitBreakers.isNullOrEmpty()) {
                        WarningsCard(
                            warnings = status.warnings ?: emptyList(),
                            circuitBreakers = status.activeCircuitBreakers ?: emptyList()
                        )
                    }
                } ?: run {
                    EmptyStateCard(message = "No risk status data available")
                }
            }
        }
    }
}

@Composable
private fun StatusCard(status: com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto) {
    val statusColor = when (status.status?.lowercase() ?: "") {
        "active", "ok", "normal" -> MaterialTheme.colorScheme.primaryContainer
        "warning" -> MaterialTheme.colorScheme.errorContainer
        "breach", "paused", "no_config" -> MaterialTheme.colorScheme.error
        else -> MaterialTheme.colorScheme.surfaceVariant
    }
    
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
        colors = CardDefaults.cardColors(containerColor = statusColor)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.CardPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(
                    shape = MaterialTheme.shapes.medium,
                    color = MaterialTheme.colorScheme.surface
                ) {
                    Text(
                        text = (status.status ?: "Unknown").uppercase(),
                        modifier = Modifier.padding(horizontal = Spacing.Medium, vertical = Spacing.Small),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            
            HorizontalDivider()
            
            Column(
                verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
            ) {
                Text(
                    text = "Account: ${status.accountId ?: "All Accounts"}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    text = "Last Updated: ${java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date())}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun ProgressBarsCard(
    status: com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto,
    riskConfig: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto? = null
) {
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
            Text(
                text = "Risk Limits Progress",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            
            // Portfolio Exposure Progress Bar
            status.totalExposure?.let { exposure ->
                val limit = riskConfig?.maxPortfolioExposureUsdt
                ProgressBarItem(
                    label = "Portfolio Exposure",
                    current = exposure,
                    limit = limit,
                    unit = " USDT",
                    isNegative = false
                )
            }
            
            // Daily Loss Progress Bar
            status.dailyPnL?.let { dailyPnL ->
                // For loss, show as negative progress
                if (dailyPnL < 0) {
                    val limit = riskConfig?.maxDailyLossUsdt?.let { -it } // Negative for loss
                    ProgressBarItem(
                        label = "Daily Loss",
                        current = Math.abs(dailyPnL),
                        limit = limit?.let { Math.abs(it) },
                        unit = " USDT",
                        isNegative = true
                    )
                }
            }
            
            // Weekly Loss Progress Bar
            status.weeklyPnL?.let { weeklyPnL ->
                if (weeklyPnL < 0) {
                    val limit = riskConfig?.maxWeeklyLossUsdt?.let { -it } // Negative for loss
                    ProgressBarItem(
                        label = "Weekly Loss",
                        current = Math.abs(weeklyPnL),
                        limit = limit?.let { Math.abs(it) },
                        unit = " USDT",
                        isNegative = true
                    )
                }
            }
            
            // Drawdown Progress Bar
            status.currentDrawdownPct?.let { current ->
                val limit = status.maxDrawdownLimitPct ?: riskConfig?.maxDrawdownPct
                if (limit != null) {
                    ProgressBarItem(
                        label = "Drawdown",
                        current = current * 100, // Convert to percentage
                        limit = limit * 100,
                        unit = "%",
                        isNegative = false
                    )
                }
            }
        }
    }
}

@Composable
private fun ProgressBarItem(
    label: String,
    current: Double,
    limit: Double?,
    unit: String,
    isNegative: Boolean
) {
    if (limit == null || limit == 0.0) {
        // Show current value without progress bar if no limit
        MetricRow(
            label = label,
            value = "${String.format("%.2f", current)}$unit",
            modifier = Modifier.padding(vertical = Spacing.Small)
        )
        return
    }
    
    val percentage = if (isNegative && limit < 0) {
        Math.abs((current / limit) * 100)
    } else if (!isNegative && limit > 0) {
        (current / limit) * 100
    } else {
        0.0
    }.coerceIn(0.0, 100.0)
    
    val barColor = when {
        percentage >= 90 -> MaterialTheme.colorScheme.error
        percentage >= 80 -> androidx.compose.ui.graphics.Color(0xFFFFC107) // Yellow
        percentage >= 60 -> androidx.compose.ui.graphics.Color(0xFFFF9800) // Orange
        else -> MaterialTheme.colorScheme.primary
    }
    
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = Spacing.Small),
        verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold
            )
            Text(
                text = "${String.format("%.2f", current)}$unit / ${String.format("%.2f", limit)}$unit (${String.format("%.0f", percentage)}%)",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        
        LinearProgressIndicator(
            progress = { (percentage / 100).toFloat() },
            modifier = Modifier
                .fillMaxWidth()
                .height(8.dp),
            color = barColor,
            trackColor = MaterialTheme.colorScheme.surfaceVariant
        )
    }
}

@Composable
private fun MetricsGridCard(
    status: com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto,
    portfolioMetrics: com.binancebot.mobile.data.remote.dto.PortfolioRiskMetricsDto? = null
) {
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
            Text(
                text = "Key Metrics",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            
            // Metrics Grid - 6 key metrics matching web app
            Column(
                verticalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                // Row 1: Total PnL, Win Rate
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    MetricCard(
                        label = "Total PnL",
                        value = portfolioMetrics?.let { metrics ->
                            metrics.totalPnL?.let {
                                FormatUtils.formatCurrency(it)
                            } ?: run {
                                val totalPnL = (metrics.dailyPnLUsdt ?: 0.0) + (metrics.weeklyPnLUsdt ?: 0.0)
                                if (totalPnL != 0.0) FormatUtils.formatCurrency(totalPnL) else "N/A"
                            }
                        } ?: status.dailyPnL?.let { 
                            FormatUtils.formatCurrency(it)
                        } ?: "N/A",
                        valueColor = portfolioMetrics?.let { metrics ->
                            metrics.totalPnL?.let {
                                if (it >= 0) MaterialTheme.colorScheme.primary 
                                else MaterialTheme.colorScheme.error
                            } ?: run {
                                val totalPnL = (metrics.dailyPnLUsdt ?: 0.0) + (metrics.weeklyPnLUsdt ?: 0.0)
                                if (totalPnL != 0.0) {
                                    if (totalPnL >= 0) MaterialTheme.colorScheme.primary 
                                    else MaterialTheme.colorScheme.error
                                } else null
                            }
                        } ?: status.dailyPnL?.let {
                            if (it >= 0) MaterialTheme.colorScheme.primary 
                            else MaterialTheme.colorScheme.error
                        },
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        label = "Win Rate",
                        value = portfolioMetrics?.winRate?.let { winRate ->
                            // API returns win_rate as percentage (e.g., 36.11), not decimal (0.3611)
                            val percentage = if (winRate > 1.0) winRate else winRate * 100
                            "${String.format("%.2f", percentage)}%"
                        } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                }
                
                // Row 2: Profit Factor, Sharpe Ratio
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    MetricCard(
                        label = "Profit Factor",
                        value = portfolioMetrics?.profitFactor?.let { 
                            String.format("%.2f", it)
                        } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        label = "Sharpe Ratio",
                        value = portfolioMetrics?.sharpeRatio?.let { 
                            String.format("%.2f", it)
                        } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                }
                
                // Row 3: Max Drawdown, Current Balance
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    MetricCard(
                        label = "Max Drawdown",
                        value = status.maxDrawdownPct?.let { 
                            "${String.format("%.2f", it * 100)}%"
                        } ?: portfolioMetrics?.maxDrawdownPct?.let {
                            "${String.format("%.2f", it * 100)}%"
                        } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        label = "Current Balance",
                        value = portfolioMetrics?.let { metrics ->
                            (metrics.totalBalanceUsdt ?: metrics.currentBalance)?.let {
                                FormatUtils.formatCurrency(it)
                            } ?: "N/A"
                        } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }
    }
}

@Composable
private fun MetricCard(
    label: String,
    value: String,
    valueColor: androidx.compose.ui.graphics.Color? = null,
    modifier: Modifier = Modifier
) {
    Column(modifier = modifier) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = valueColor ?: MaterialTheme.colorScheme.onSurface
        )
    }
}

@Composable
private fun WarningsCard(
    warnings: List<String>,
    circuitBreakers: List<String>
) {
    if (warnings.isNotEmpty() || circuitBreakers.isNotEmpty()) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.errorContainer
            )
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(Spacing.CardPadding),
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                if (warnings.isNotEmpty()) {
                    Text(
                        text = "⚠️ Warnings",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onErrorContainer
                    )
                    warnings.forEach { warning ->
                        Text(
                            text = "• $warning",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            modifier = Modifier.padding(start = Spacing.Small)
                        )
                    }
                }
                
                if (circuitBreakers.isNotEmpty()) {
                    if (warnings.isNotEmpty()) {
                        HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                    }
                    Text(
                        text = "🔴 Active Circuit Breakers",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onErrorContainer
                    )
                    circuitBreakers.forEach { breaker ->
                        Text(
                            text = "• $breaker",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            modifier = Modifier.padding(start = Spacing.Small)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun EmptyStateCard(message: String) {
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
                text = message,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

// Portfolio Metrics Tab
@Composable
fun PortfolioMetricsTab(
    portfolioMetrics: com.binancebot.mobile.data.remote.dto.PortfolioRiskMetricsDto?,
    uiState: RiskManagementUiState,
    onRetry: () -> Unit,
    viewModel: RiskManagementViewModel,
    accountId: String?
) {
    LaunchedEffect(accountId) {
        viewModel.loadPortfolioMetrics(accountId)
    }
    
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
                if (portfolioMetrics == null) {
                    EmptyStateCard(message = "No portfolio metrics data available. Please refresh or check your account.")
                } else {
                    portfolioMetrics.let { metrics ->
                        // Balance Metrics
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
                            Text(
                                text = "Balance Metrics",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold
                            )
                            HorizontalDivider()
                            
                            (metrics.totalBalanceUsdt ?: metrics.currentBalance)?.let {
                                MetricRow("Total Balance", FormatUtils.formatCurrency(it))
                            }
                            metrics.availableBalanceUsdt?.let {
                                MetricRow("Available Balance", FormatUtils.formatCurrency(it))
                            }
                            metrics.usedMarginUsdt?.let {
                                MetricRow("Used Margin", FormatUtils.formatCurrency(it))
                            }
                            (metrics.peakBalanceUsdt ?: metrics.peakBalance)?.let {
                                MetricRow("Peak Balance", FormatUtils.formatCurrency(it))
                            }
                        }
                    }
                    
                    // Performance Metrics
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
                            Text(
                                text = "Performance Metrics",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold
                            )
                            HorizontalDivider()
                            
                            metrics.totalTrades?.let {
                                MetricRow("Total Trades", it.toString())
                            }
                            metrics.winningTrades?.let { wins ->
                                metrics.losingTrades?.let { losses ->
                                    MetricRow("Wins / Losses", "$wins / $losses")
                                }
                            }
                            metrics.winRate?.let { winRate ->
                                val percentage = if (winRate > 1.0) winRate else winRate * 100
                                MetricRow("Win Rate", "${String.format("%.2f", percentage)}%")
                            }
                            metrics.profitFactor?.let {
                                MetricRow("Profit Factor", String.format("%.2f", it))
                            }
                            metrics.sharpeRatio?.let {
                                MetricRow("Sharpe Ratio", String.format("%.2f", it))
                            }
                            metrics.avgWin?.let {
                                MetricRow("Avg Win", FormatUtils.formatCurrency(it))
                            }
                            metrics.avgLoss?.let {
                                MetricRow("Avg Loss", FormatUtils.formatCurrency(it))
                            }
                        }
                    }
                    
                    // Risk Metrics
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
                            Text(
                                text = "Risk Metrics",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold
                            )
                            HorizontalDivider()
                            
                            metrics.totalExposureUsdt?.let {
                                MetricRow("Total Exposure", FormatUtils.formatCurrency(it))
                            }
                            metrics.totalExposurePct?.let {
                                MetricRow("Exposure %", "${String.format("%.2f", it * 100)}%")
                            }
                            metrics.maxDrawdownPct?.let {
                                MetricRow("Max Drawdown", "${String.format("%.2f", it * 100)}%")
                            }
                            metrics.currentDrawdownPct?.let {
                                MetricRow("Current Drawdown", "${String.format("%.2f", it * 100)}%")
                            }
                            metrics.dailyPnLUsdt?.let {
                                MetricRow("Daily PnL", FormatUtils.formatCurrency(it))
                            }
                            metrics.weeklyPnLUsdt?.let {
                                MetricRow("Weekly PnL", FormatUtils.formatCurrency(it))
                            }
                        }
                    }
                    }
                }
            }
        }
    }
}

// Strategy Metrics Tab
@Composable
fun StrategyMetricsTab(
    strategyMetrics: List<com.binancebot.mobile.data.remote.dto.StrategyRiskMetricsDto>,
    uiState: RiskManagementUiState,
    viewModel: RiskManagementViewModel,
    accountId: String?
) {
    LaunchedEffect(accountId) {
        viewModel.loadAllStrategyMetrics(accountId)
    }
    
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
                onRetry = { viewModel.loadAllStrategyMetrics(accountId) },
                modifier = Modifier.fillMaxSize()
            )
        }
        else -> {
            if (strategyMetrics.isEmpty()) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    EmptyStateCard(message = "No strategy metrics available")
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(horizontal = Spacing.ScreenPadding, vertical = Spacing.ScreenPadding),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    items(
                        items = strategyMetrics,
                        key = { it.strategyId }
                    ) { strategyMetric ->
                        StrategyMetricCard(
                            strategyMetric = strategyMetric,
                            viewModel = viewModel
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StrategyMetricCard(
    strategyMetric: com.binancebot.mobile.data.remote.dto.StrategyRiskMetricsDto,
    viewModel: RiskManagementViewModel
) {
    var showConfigDialog by remember { mutableStateOf(false) }
    
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
                Column {
                    Text(
                        text = strategyMetric.strategyName?.takeIf { it.isNotBlank() } 
                            ?: strategyMetric.strategyId,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    strategyMetric.symbol?.let {
                        Text(
                            text = it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                Button(
                    onClick = { showConfigDialog = true },
                    modifier = Modifier.height(36.dp)
                ) {
                    Text("Risk Config", style = MaterialTheme.typography.labelSmall)
                }
            }
            
            HorizontalDivider()
            
            strategyMetric.metrics?.let { metrics ->
                // Row 1: Total Trades, Win Rate (matching web app)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    MetricCard(
                        label = "Total Trades",
                        value = metrics.totalTrades?.toString() ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        label = "Win Rate",
                        value = metrics.winRate?.let { winRate ->
                            // API returns win_rate as percentage (e.g., 36.11), not decimal (0.3611)
                            val percentage = if (winRate > 1.0) winRate else winRate * 100
                            "${String.format("%.2f", percentage)}%"
                        } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                }
                
                // Row 2: Total PnL, Max Drawdown (matching web app)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    val totalPnL = metrics.totalPnL ?: ((metrics.dailyPnLUsdt ?: 0.0) + (metrics.weeklyPnLUsdt ?: 0.0))
                    MetricCard(
                        label = "Total PnL",
                        value = if (totalPnL != 0.0) FormatUtils.formatCurrency(totalPnL) else "N/A",
                        valueColor = if (totalPnL != 0.0) {
                            if (totalPnL >= 0) MaterialTheme.colorScheme.primary 
                            else MaterialTheme.colorScheme.error
                        } else null,
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        label = "Max Drawdown",
                        value = metrics.maxDrawdownPct?.let { drawdown ->
                            // API returns max_drawdown_pct as percentage (e.g., 2.18), not decimal (0.0218)
                            val percentage = if (drawdown > 1.0) drawdown else drawdown * 100
                            "${String.format("%.2f", percentage)}%"
                        } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                }
                
                // Additional metrics (matching web app)
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                metrics.profitFactor?.let {
                    MetricRow("Profit Factor", String.format("%.2f", it))
                }
                metrics.sharpeRatio?.let {
                    MetricRow("Sharpe Ratio", String.format("%.2f", it))
                }
            } ?: run {
                Text(
                    text = strategyMetric.message ?: "No metrics available",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
    
    if (showConfigDialog) {
        StrategyRiskConfigDialog(
            strategyId = strategyMetric.strategyId,
            strategyName = strategyMetric.strategyName,
            onDismiss = { showConfigDialog = false },
            viewModel = viewModel
        )
    }
}

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

// Reports Tab
@Composable
fun ReportsTab(
    dailyReport: com.binancebot.mobile.data.remote.dto.RiskReportDto?,
    weeklyReport: com.binancebot.mobile.data.remote.dto.RiskReportDto?,
    uiState: RiskManagementUiState,
    viewModel: RiskManagementViewModel,
    accountId: String?
) {
    var reportType by remember { mutableStateOf<String?>(null) }
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(Spacing.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            Button(
                onClick = {
                    reportType = "daily"
                    viewModel.loadDailyReport(accountId)
                },
                modifier = Modifier.weight(1f),
                enabled = uiState !is RiskManagementUiState.Loading
            ) {
                Text("Daily Report")
            }
            Button(
                onClick = {
                    reportType = "weekly"
                    viewModel.loadWeeklyReport(accountId)
                },
                modifier = Modifier.weight(1f),
                enabled = uiState !is RiskManagementUiState.Loading
            ) {
                Text("Weekly Report")
            }
        }
        
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
                    onRetry = {
                        when (reportType) {
                            "daily" -> viewModel.loadDailyReport(accountId)
                            "weekly" -> viewModel.loadWeeklyReport(accountId)
                            else -> {}
                        }
                    },
                    modifier = Modifier.fillMaxSize()
                )
            }
            else -> {
                val report = when (reportType) {
                    "daily" -> dailyReport
                    "weekly" -> weeklyReport
                    else -> null
                }
                
                if (report != null) {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        item {
                            RiskReportCard(report = report, reportType = reportType ?: "")
                        }
                    }
                } else {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        EmptyStateCard(message = "Select a report type to view")
                    }
                }
            }
        }
    }
}

@Composable
private fun RiskReportCard(
    report: com.binancebot.mobile.data.remote.dto.RiskReportDto,
    reportType: String
) {
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
            Text(
                text = if (reportType == "daily") {
                    "Daily Risk Report - ${report.date ?: "N/A"}"
                } else {
                    "Weekly Risk Report - ${report.weekStart ?: "N/A"} to ${report.weekEnd ?: "N/A"}"
                },
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            
            report.totalTrades?.let {
                MetricRow("Total Trades", it.toString())
            }
            report.winRate?.let { winRate ->
                val percentage = if (winRate > 1.0) winRate else winRate * 100
                MetricRow("Win Rate", "${String.format("%.2f", percentage)}%")
            }
            report.totalPnL?.let {
                MetricRow(
                    "Total PnL",
                    FormatUtils.formatCurrency(it),
                    valueColor = if (it >= 0) MaterialTheme.colorScheme.primary 
                    else MaterialTheme.colorScheme.error
                )
            }
            report.profitFactor?.let {
                MetricRow("Profit Factor", String.format("%.2f", it))
            }
            report.maxDrawdownPct?.let { drawdown ->
                val percentage = if (drawdown > 1.0) drawdown else drawdown * 100
                MetricRow("Max Drawdown", "${String.format("%.2f", percentage)}%")
            }
            report.sharpeRatio?.let {
                MetricRow("Sharpe Ratio", String.format("%.2f", it))
            }
            if (reportType == "daily") {
                report.dailyLoss?.let {
                    MetricRow("Daily Loss", FormatUtils.formatCurrency(it))
                }
            } else {
                report.weeklyLoss?.let {
                    MetricRow("Weekly Loss", FormatUtils.formatCurrency(it))
                }
            }
        }
    }
}

// Configuration Tab - Lists all accounts with their configurations
@Composable
fun ConfigurationTab(
    riskConfig: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?,
    onRetry: () -> Unit,
    viewModel: RiskManagementViewModel,
    accountId: String?
) {
    val accountViewModel: com.binancebot.mobile.presentation.viewmodel.AccountViewModel = androidx.hilt.navigation.compose.hiltViewModel()
    val accounts by accountViewModel.accounts.collectAsState()
    val allAccountConfigs by viewModel.allAccountConfigs.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
    var expandedAccountIds by remember { mutableStateOf<Set<String>>(emptySet()) }
    var showEditDialog by remember { mutableStateOf(false) }
    var editingAccountId by remember { mutableStateOf<String?>(null) }
    var editingConfig by remember { mutableStateOf<com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?>(null) }
    
    // Load all account configs when accounts are loaded
    LaunchedEffect(accounts) {
        if (accounts.isNotEmpty()) {
            val accountIds = accounts.map { it.accountId } + listOf("default")
            viewModel.loadAllAccountConfigs(accountIds)
        }
    }
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(Spacing.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
    ) {
        // Header with Create button
        Text(
            text = "Risk Configurations",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold
        )
        
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
                    onRetry = {
                        if (accounts.isNotEmpty()) {
                            val accountIds = accounts.map { it.accountId } + listOf("default")
                            viewModel.loadAllAccountConfigs(accountIds)
                        }
                    },
                    modifier = Modifier.fillMaxSize()
                )
            }
            else -> {
                if (accounts.isEmpty()) {
                    EmptyStateCard(message = "No accounts found. Please create an account first.")
                } else {
                    LazyColumn(
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        // Default account
                        item {
                            AccountConfigCard(
                                accountId = "default",
                                accountName = "Default Account",
                                isTestnet = false,
                                config = allAccountConfigs["default"],
                                isExpanded = expandedAccountIds.contains("default"),
                                onExpandedChange = { expanded ->
                                    expandedAccountIds = if (expanded) {
                                        expandedAccountIds + "default"
                                    } else {
                                        expandedAccountIds - "default"
                                    }
                                },
                                onEdit = {
                                    editingAccountId = "default"
                                    editingConfig = allAccountConfigs["default"]
                                    showEditDialog = true
                                },
                                onCreate = {
                                    editingAccountId = "default"
                                    editingConfig = null
                                    showEditDialog = true
                                }
                            )
                        }
                        
                        // All other accounts
                        items(accounts.size) { index ->
                            val account = accounts[index]
                            AccountConfigCard(
                                accountId = account.accountId,
                                accountName = account.name ?: account.accountId,
                                isTestnet = account.testnet,
                                config = allAccountConfigs[account.accountId],
                                isExpanded = expandedAccountIds.contains(account.accountId),
                                onExpandedChange = { expanded ->
                                    expandedAccountIds = if (expanded) {
                                        expandedAccountIds + account.accountId
                                    } else {
                                        expandedAccountIds - account.accountId
                                    }
                                },
                                onEdit = {
                                    editingAccountId = account.accountId
                                    editingConfig = allAccountConfigs[account.accountId]
                                    showEditDialog = true
                                },
                                onCreate = {
                                    editingAccountId = account.accountId
                                    editingConfig = null
                                    showEditDialog = true
                                }
                            )
                        }
                    }
                }
            }
        }
    }
    
    // Show loading/error states for edit/create
    when (uiState) {
        is RiskManagementUiState.Success -> {
            LaunchedEffect(Unit) {
                if (showEditDialog) {
                    // Reload configs after save
                    if (accounts.isNotEmpty()) {
                        val accountIds = accounts.map { it.accountId } + listOf("default")
                        viewModel.loadAllAccountConfigs(accountIds)
                    }
                    showEditDialog = false
                }
            }
        }
        else -> {}
    }
    
    // Edit/Create Configuration Dialog
    if (showEditDialog) {
        EditRiskConfigDialog(
            config = editingConfig,
            isEdit = editingConfig != null,
            isLoading = uiState is RiskManagementUiState.Loading,
            errorMessage = (uiState as? RiskManagementUiState.Error)?.message,
            onDismiss = { 
                showEditDialog = false
                editingAccountId = null
                editingConfig = null
            },
            onSave = { updatedConfig ->
                if (editingConfig != null) {
                    viewModel.updateRiskConfig(editingAccountId, updatedConfig)
                } else {
                    viewModel.createRiskConfig(editingAccountId, updatedConfig)
                }
            },
            defaultAccountId = editingAccountId
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AccountConfigCard(
    accountId: String,
    accountName: String,
    isTestnet: Boolean,
    config: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?,
    isExpanded: Boolean,
    onExpandedChange: (Boolean) -> Unit,
    onEdit: () -> Unit,
    onCreate: () -> Unit
) {
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
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .clickable { onExpandedChange(!isExpanded) }
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                    ) {
                        Text(
                            text = accountName,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        if (isTestnet) {
                            Surface(
                                shape = MaterialTheme.shapes.small,
                                color = MaterialTheme.colorScheme.secondaryContainer
                            ) {
                                Text(
                                    text = "Testnet",
                                    modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSecondaryContainer
                                )
                            }
                        }
                    }
                    Text(
                        text = "Account ID: $accountId",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    if (config != null) {
                        IconButton(
                            onClick = { onEdit() },
                            modifier = Modifier.size(40.dp)
                        ) {
                            Icon(
                                Icons.Filled.Edit,
                                contentDescription = "Edit",
                                modifier = Modifier.size(20.dp)
                            )
                        }
                    } else {
                        Button(
                            onClick = { onCreate() },
                            modifier = Modifier.height(36.dp)
                        ) {
                            Icon(Icons.Filled.Add, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(Spacing.Tiny))
                            Text("Create", style = MaterialTheme.typography.labelSmall)
                        }
                    }
                    
                    IconButton(
                        onClick = { onExpandedChange(!isExpanded) },
                        modifier = Modifier.size(40.dp)
                    ) {
                        Icon(
                            if (isExpanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore,
                            contentDescription = if (isExpanded) "Collapse" else "Expand"
                        )
                    }
                }
            }
            
            // Status indicator
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(
                    shape = MaterialTheme.shapes.small,
                    color = if (config != null) {
                        MaterialTheme.colorScheme.primaryContainer
                    } else {
                        MaterialTheme.colorScheme.surfaceVariant
                    }
                ) {
                    Text(
                        text = if (config != null) "✓ Configured" else "⚠ Not Configured",
                        modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                        style = MaterialTheme.typography.labelSmall,
                        color = if (config != null) {
                            MaterialTheme.colorScheme.onPrimaryContainer
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            
            // Expanded details (hidden by default)
            if (isExpanded && config != null) {
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                
                // Portfolio Limits Summary
                Column(
                    verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
                ) {
                    Text(
                        text = "Portfolio Limits",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary
                    )
                    config.maxPortfolioExposureUsdt?.let {
                        Text(
                            text = "• Max Exposure: ${FormatUtils.formatCurrency(it)}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    config.maxDailyLossUsdt?.let {
                        Text(
                            text = "• Max Daily Loss: ${FormatUtils.formatCurrency(it)}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    config.maxWeeklyLossUsdt?.let {
                        Text(
                            text = "• Max Weekly Loss: ${FormatUtils.formatCurrency(it)}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    config.maxDrawdownPct?.let {
                        Text(
                            text = "• Max Drawdown: ${String.format("%.2f", it * 100)}%",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
                
                // Circuit Breaker Summary
                if (config.circuitBreakerEnabled) {
                    HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                    Column(
                        verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
                    ) {
                        Text(
                            text = "Circuit Breaker",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary
                        )
                        Text(
                            text = "• Enabled: Yes",
                            style = MaterialTheme.typography.bodySmall
                        )
                        config.maxConsecutiveLosses?.let {
                            Text(
                                text = "• Max Consecutive Losses: $it",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                }
                
                // Advanced Settings Summary
                val advancedEnabled = listOf(
                    config.volatilityBasedSizingEnabled to "Volatility-Based Sizing",
                    config.performanceBasedAdjustmentEnabled to "Performance-Based Adjustment",
                    config.kellyCriterionEnabled to "Kelly Criterion",
                    config.correlationLimitsEnabled to "Correlation Limits",
                    config.marginCallProtectionEnabled to "Margin Protection"
                ).filter { it.first }.map { it.second }
                
                if (advancedEnabled.isNotEmpty()) {
                    HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                    Column(
                        verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
                    ) {
                        Text(
                            text = "Advanced Settings",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary
                        )
                        advancedEnabled.forEach { setting ->
                            Text(
                                text = "• $setting: Enabled",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                }
            } else if (isExpanded && config == null) {
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                Text(
                    text = "No risk configuration found for this account. Click 'Create' to set up risk management.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun ConfigurationSection(
    title: String,
    items: List<String>
) {
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
                text = title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            items.forEach { item ->
                Text(
                    text = item,
                    style = MaterialTheme.typography.bodyMedium
                )
            }
        }
    }
}

@Composable
fun StrategyRiskConfigDialog(
    strategyId: String,
    strategyName: String?,
    onDismiss: () -> Unit,
    viewModel: RiskManagementViewModel
) {
    val strategyConfig by viewModel.strategyRiskConfig.collectAsState()
    var isLoading by remember(strategyId) { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var configLoaded by remember(strategyId) { mutableStateOf(false) }
    
    // Load existing config when dialog opens
    LaunchedEffect(strategyId) {
        if (!configLoaded) {
            isLoading = true
            errorMessage = null
            viewModel.loadStrategyRiskConfig(strategyId)
            configLoaded = true
        }
    }
    
    // Observe strategyConfig changes
    LaunchedEffect(strategyConfig) {
        isLoading = false
        errorMessage = null
    }
    
    // Handle errors from ViewModel (but don't rely on shared uiState)
    val scope = rememberCoroutineScope()
    
    val config = strategyConfig
    val isEdit = config != null
    
    // State variables
    var enabled by remember { mutableStateOf(config?.enabled ?: true) }
    var maxDailyLossUsdt by remember { mutableStateOf(config?.maxDailyLossUsdt?.toString() ?: "") }
    var maxDailyLossPct by remember { mutableStateOf((config?.maxDailyLossPct?.times(100))?.toString() ?: "") }
    var maxWeeklyLossUsdt by remember { mutableStateOf(config?.maxWeeklyLossUsdt?.toString() ?: "") }
    var maxWeeklyLossPct by remember { mutableStateOf((config?.maxWeeklyLossPct?.times(100))?.toString() ?: "") }
    var maxDrawdownPct by remember { mutableStateOf((config?.maxDrawdownPct?.times(100))?.toString() ?: "") }
    var overrideAccountLimits by remember { mutableStateOf(config?.overrideAccountLimits ?: false) }
    var useMoreRestrictive by remember { mutableStateOf(config?.useMoreRestrictive ?: true) }
    
    // Update state when config loads
    LaunchedEffect(config) {
        if (config != null) {
            enabled = config.enabled
            maxDailyLossUsdt = config.maxDailyLossUsdt?.toString() ?: ""
            maxDailyLossPct = (config.maxDailyLossPct?.times(100))?.toString() ?: ""
            maxWeeklyLossUsdt = config.maxWeeklyLossUsdt?.toString() ?: ""
            maxWeeklyLossPct = (config.maxWeeklyLossPct?.times(100))?.toString() ?: ""
            maxDrawdownPct = (config.maxDrawdownPct?.times(100))?.toString() ?: ""
            overrideAccountLimits = config.overrideAccountLimits
            useMoreRestrictive = config.useMoreRestrictive
            isLoading = false
        } else {
            // If config is null after loading, it means no config exists (404)
            isLoading = false
        }
    }
    
    fun createUpdatedConfig(): com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto {
        return com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto(
            id = config?.id,
            strategyId = strategyId,
            enabled = enabled,
            maxDailyLossUsdt = maxDailyLossUsdt.toDoubleOrNull(),
            maxDailyLossPct = maxDailyLossPct.toDoubleOrNull()?.div(100),
            maxWeeklyLossUsdt = maxWeeklyLossUsdt.toDoubleOrNull(),
            maxWeeklyLossPct = maxWeeklyLossPct.toDoubleOrNull()?.div(100),
            maxDrawdownPct = maxDrawdownPct.toDoubleOrNull()?.div(100),
            overrideAccountLimits = overrideAccountLimits,
            useMoreRestrictive = useMoreRestrictive
        )
    }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Strategy Risk Config: ${strategyName ?: strategyId}") },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                if (errorMessage != null && !errorMessage!!.contains("404") && !errorMessage!!.contains("not found")) {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        )
                    ) {
                        Text(
                            text = errorMessage ?: "",
                            modifier = Modifier.padding(Spacing.Medium),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                    }
                }
                
                // Enabled toggle
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Enabled")
                    Switch(
                        checked = enabled,
                        onCheckedChange = { enabled = it },
                        enabled = !isLoading
                    )
                }
                
                HorizontalDivider()
                
                // Loss Limits
                Text(
                    text = "Loss Limits",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                OutlinedTextField(
                    value = maxDailyLossUsdt,
                    onValueChange = { maxDailyLossUsdt = it },
                    label = { Text("Max Daily Loss (USDT)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading && enabled
                )
                OutlinedTextField(
                    value = maxDailyLossPct,
                    onValueChange = { maxDailyLossPct = it },
                    label = { Text("Max Daily Loss (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading && enabled
                )
                OutlinedTextField(
                    value = maxWeeklyLossUsdt,
                    onValueChange = { maxWeeklyLossUsdt = it },
                    label = { Text("Max Weekly Loss (USDT)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading && enabled
                )
                OutlinedTextField(
                    value = maxWeeklyLossPct,
                    onValueChange = { maxWeeklyLossPct = it },
                    label = { Text("Max Weekly Loss (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading && enabled
                )
                OutlinedTextField(
                    value = maxDrawdownPct,
                    onValueChange = { maxDrawdownPct = it },
                    label = { Text("Max Drawdown (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading && enabled
                )
                
                HorizontalDivider()
                
                // Priority Mode
                Text(
                    text = "Priority Mode",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Override Account Limits")
                    Switch(
                        checked = overrideAccountLimits,
                        onCheckedChange = { 
                            overrideAccountLimits = it
                            if (it) useMoreRestrictive = false
                        },
                        enabled = !isLoading && enabled
                    )
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Use More Restrictive")
                    Switch(
                        checked = useMoreRestrictive,
                        onCheckedChange = { 
                            useMoreRestrictive = it
                            if (it) overrideAccountLimits = false
                        },
                        enabled = !isLoading && enabled && !overrideAccountLimits
                    )
                }
                Text(
                    text = if (overrideAccountLimits) {
                        "Strategy limits will completely replace account limits"
                    } else if (useMoreRestrictive) {
                        "The most restrictive limit will be used (minimum for losses, maximum for exposure)"
                    } else {
                        "Strategy limits will be ignored, only account limits apply"
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val updatedConfig = createUpdatedConfig()
                    isLoading = true
                    scope.launch {
                        try {
                            if (isEdit) {
                                viewModel.updateStrategyRiskConfig(strategyId, updatedConfig)
                            } else {
                                viewModel.createStrategyRiskConfig(updatedConfig)
                            }
                            // Wait a bit for the operation to complete
                            kotlinx.coroutines.delay(500)
                            isLoading = false
                            onDismiss() // Close dialog after successful save
                        } catch (e: Exception) {
                            isLoading = false
                            errorMessage = e.message
                        }
                    }
                },
                enabled = !isLoading
            ) {
                Text(if (isEdit) "Update" else "Create")
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isLoading
            ) {
                Text("Cancel")
            }
        }
    )
}

@Composable
fun MetricRow(
    label: String,
    value: String,
    valueColor: androidx.compose.ui.graphics.Color? = null,
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
            fontWeight = FontWeight.Bold,
            color = valueColor ?: MaterialTheme.colorScheme.onSurface
        )
    }
}

private fun formatTimestamp(timestamp: String): String {
    return try {
        val sdf = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.getDefault())
        val date = java.time.Instant.parse(timestamp).atZone(java.time.ZoneId.systemDefault()).toLocalDateTime()
        java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss").format(date)
    } catch (e: Exception) {
        timestamp
    }
}

// Enhanced EditRiskConfigDialog with all features (continuing from existing implementation)
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EditRiskConfigDialog(
    config: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?,
    isEdit: Boolean,
    isLoading: Boolean,
    errorMessage: String?,
    onDismiss: () -> Unit,
    onSave: (com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto) -> Unit,
    defaultAccountId: String? = null
) {
    // Load accounts for selection
    val accountViewModel: com.binancebot.mobile.presentation.viewmodel.AccountViewModel = androidx.hilt.navigation.compose.hiltViewModel()
    val accounts by accountViewModel.accounts.collectAsState()
    
    var selectedAccountId by remember { mutableStateOf<String?>(config?.accountId ?: defaultAccountId) }
    var showAccountDropdown by remember { mutableStateOf(false) }
    var accountError by remember { mutableStateOf<String?>(null) }
    
    // Auto-select first account if available and creating new config
    LaunchedEffect(accounts) {
        if (!isEdit && accounts.isNotEmpty() && selectedAccountId == null) {
            selectedAccountId = accounts.first().accountId
            accountError = null
        }
    }
    // State variables for all configuration fields
    var maxPortfolioExposureUsdt by remember { mutableStateOf(config?.maxPortfolioExposureUsdt?.toString() ?: "") }
    var maxPortfolioExposurePct by remember { mutableStateOf((config?.maxPortfolioExposurePct?.times(100))?.toString() ?: "") }
    var maxDailyLossUsdt by remember { mutableStateOf(config?.maxDailyLossUsdt?.toString() ?: "") }
    var maxDailyLossPct by remember { mutableStateOf((config?.maxDailyLossPct?.times(100))?.toString() ?: "") }
    var maxWeeklyLossUsdt by remember { mutableStateOf(config?.maxWeeklyLossUsdt?.toString() ?: "") }
    var maxWeeklyLossPct by remember { mutableStateOf((config?.maxWeeklyLossPct?.times(100))?.toString() ?: "") }
    var maxDrawdownPct by remember { mutableStateOf((config?.maxDrawdownPct?.times(100))?.toString() ?: "") }
    
    // Loss Reset
    var dailyLossResetTime by remember { mutableStateOf(config?.dailyLossResetTime ?: "00:00:00") }
    var weeklyLossResetDay by remember { mutableStateOf(config?.weeklyLossResetDay?.toString() ?: "1") }
    var timezone by remember { mutableStateOf(config?.timezone ?: "UTC") }
    
    // Circuit Breaker
    var circuitBreakerEnabled by remember { mutableStateOf(config?.circuitBreakerEnabled ?: false) }
    var maxConsecutiveLosses by remember { mutableStateOf(config?.maxConsecutiveLosses?.toString() ?: "") }
    var rapidLossThresholdPct by remember { mutableStateOf((config?.rapidLossThresholdPct?.times(100))?.toString() ?: "") }
    var rapidLossTimeframeMinutes by remember { mutableStateOf(config?.rapidLossTimeframeMinutes?.toString() ?: "") }
    var circuitBreakerCooldownMinutes by remember { mutableStateOf(config?.circuitBreakerCooldownMinutes?.toString() ?: "") }
    
    // Dynamic Settings
    var volatilityBasedSizingEnabled by remember { mutableStateOf(config?.volatilityBasedSizingEnabled ?: false) }
    var performanceBasedAdjustmentEnabled by remember { mutableStateOf(config?.performanceBasedAdjustmentEnabled ?: false) }
    var kellyCriterionEnabled by remember { mutableStateOf(config?.kellyCriterionEnabled ?: false) }
    var kellyFraction by remember { mutableStateOf((config?.kellyFraction?.times(100))?.toString() ?: "25") }
    
    // Correlation Limits
    var correlationLimitsEnabled by remember { mutableStateOf(config?.correlationLimitsEnabled ?: false) }
    var maxCorrelationExposurePct by remember { mutableStateOf((config?.maxCorrelationExposurePct?.times(100))?.toString() ?: "") }
    
    // Margin Protection
    var marginCallProtectionEnabled by remember { mutableStateOf(config?.marginCallProtectionEnabled ?: true) }
    var minMarginRatio by remember { mutableStateOf((config?.minMarginRatio?.times(100))?.toString() ?: "") }
    
    // Trade Frequency
    var maxTradesPerDayPerStrategy by remember { mutableStateOf(config?.maxTradesPerDayPerStrategy?.toString() ?: "") }
    var maxTradesPerDayTotal by remember { mutableStateOf(config?.maxTradesPerDayTotal?.toString() ?: "") }
    
    // Order Size
    var autoReduceOrderSize by remember { mutableStateOf(config?.autoReduceOrderSize ?: false) }
    
    fun createUpdatedConfig(): com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto {
        // Use selected account ID, fallback to config's account ID
        val finalAccountId = selectedAccountId ?: config?.accountId
        
        return com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto(
            id = config?.id,
            accountId = finalAccountId,
            maxPortfolioExposureUsdt = maxPortfolioExposureUsdt.toDoubleOrNull(),
            maxPortfolioExposurePct = maxPortfolioExposurePct.toDoubleOrNull()?.div(100),
            maxDailyLossUsdt = maxDailyLossUsdt.toDoubleOrNull(),
            maxDailyLossPct = maxDailyLossPct.toDoubleOrNull()?.div(100),
            maxWeeklyLossUsdt = maxWeeklyLossUsdt.toDoubleOrNull(),
            maxWeeklyLossPct = maxWeeklyLossPct.toDoubleOrNull()?.div(100),
            maxDrawdownPct = maxDrawdownPct.toDoubleOrNull()?.div(100),
            dailyLossResetTime = dailyLossResetTime,
            weeklyLossResetDay = weeklyLossResetDay.toIntOrNull() ?: 1, // Default to Monday
            timezone = timezone,
            circuitBreakerEnabled = circuitBreakerEnabled,
            // Only set circuit breaker fields if enabled
            maxConsecutiveLosses = if (circuitBreakerEnabled) maxConsecutiveLosses.toIntOrNull() else null,
            rapidLossThresholdPct = if (circuitBreakerEnabled) rapidLossThresholdPct.toDoubleOrNull()?.div(100) else null,
            rapidLossTimeframeMinutes = if (circuitBreakerEnabled) rapidLossTimeframeMinutes.toIntOrNull() else null,
            circuitBreakerCooldownMinutes = if (circuitBreakerEnabled) circuitBreakerCooldownMinutes.toIntOrNull() else null,
            volatilityBasedSizingEnabled = volatilityBasedSizingEnabled,
            performanceBasedAdjustmentEnabled = performanceBasedAdjustmentEnabled,
            kellyCriterionEnabled = kellyCriterionEnabled,
            kellyFraction = if (kellyCriterionEnabled) kellyFraction.toDoubleOrNull()?.div(100) else null,
            correlationLimitsEnabled = correlationLimitsEnabled,
            maxCorrelationExposurePct = if (correlationLimitsEnabled) maxCorrelationExposurePct.toDoubleOrNull()?.div(100) else null,
            marginCallProtectionEnabled = marginCallProtectionEnabled,
            minMarginRatio = if (marginCallProtectionEnabled) minMarginRatio.toDoubleOrNull()?.div(100) else null,
            maxTradesPerDayPerStrategy = maxTradesPerDayPerStrategy.toIntOrNull(),
            maxTradesPerDayTotal = maxTradesPerDayTotal.toIntOrNull(),
            autoReduceOrderSize = autoReduceOrderSize
        )
    }
    
    AlertDialog(
        onDismissRequest = { if (!isLoading) onDismiss() },
        title = { Text(if (isEdit) "Edit Risk Configuration" else "Create Risk Configuration") },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                if (errorMessage != null) {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        )
                    ) {
                        Text(
                            text = errorMessage,
                            modifier = Modifier.padding(Spacing.Medium),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                    }
                }
                
                // Account Selection (required for new configs)
                if (!isEdit) {
                    Text(
                        text = "Account Selection *",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold
                    )
                    if (accounts.isEmpty()) {
                        Text(
                            text = "Loading accounts...",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    } else {
                        ExposedDropdownMenuBox(
                            expanded = showAccountDropdown,
                            onExpandedChange = { showAccountDropdown = !showAccountDropdown }
                        ) {
                            OutlinedTextField(
                                value = accounts.find { it.accountId == selectedAccountId }?.let { account ->
                                    "${account.name ?: account.accountId}${if (account.testnet) " (Testnet)" else ""}"
                                } ?: "Select Account",
                                onValueChange = {},
                                readOnly = true,
                                label = { Text("Account *") },
                                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = showAccountDropdown) },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .menuAnchor(),
                                singleLine = true,
                                isError = selectedAccountId == null || accountError != null,
                                supportingText = accountError?.let { { Text(it) } },
                                enabled = !isLoading
                            )
                            ExposedDropdownMenu(
                                expanded = showAccountDropdown,
                                onDismissRequest = { showAccountDropdown = false }
                            ) {
                                accounts.forEach { account ->
                                    DropdownMenuItem(
                                        text = { 
                                            Text("${account.name ?: account.accountId}${if (account.testnet) " (Testnet)" else ""}")
                                        },
                                        onClick = {
                                            selectedAccountId = account.accountId
                                            showAccountDropdown = false
                                        }
                                    )
                                }
                            }
                        }
                    }
                    HorizontalDivider()
                }
                
                // Portfolio Limits Section
                Text(
                    text = "Portfolio Limits",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                OutlinedTextField(
                    value = maxPortfolioExposureUsdt,
                    onValueChange = { maxPortfolioExposureUsdt = it },
                    label = { Text("Max Portfolio Exposure (USDT)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = maxPortfolioExposurePct,
                    onValueChange = { maxPortfolioExposurePct = it },
                    label = { Text("Max Portfolio Exposure (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = maxDailyLossUsdt,
                    onValueChange = { maxDailyLossUsdt = it },
                    label = { Text("Max Daily Loss (USDT)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = maxDailyLossPct,
                    onValueChange = { maxDailyLossPct = it },
                    label = { Text("Max Daily Loss (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = maxWeeklyLossUsdt,
                    onValueChange = { maxWeeklyLossUsdt = it },
                    label = { Text("Max Weekly Loss (USDT)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = maxWeeklyLossPct,
                    onValueChange = { maxWeeklyLossPct = it },
                    label = { Text("Max Weekly Loss (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = maxDrawdownPct,
                    onValueChange = { maxDrawdownPct = it },
                    label = { Text("Max Drawdown (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                
                HorizontalDivider()
                
                // Circuit Breaker Section
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Circuit Breaker Enabled")
                    Switch(
                        checked = circuitBreakerEnabled,
                        onCheckedChange = { circuitBreakerEnabled = it },
                        enabled = !isLoading
                    )
                }
                
                if (circuitBreakerEnabled) {
                    OutlinedTextField(
                        value = maxConsecutiveLosses,
                        onValueChange = { maxConsecutiveLosses = it },
                        label = { Text("Max Consecutive Losses") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                    OutlinedTextField(
                        value = rapidLossThresholdPct,
                        onValueChange = { rapidLossThresholdPct = it },
                        label = { Text("Rapid Loss Threshold (%)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                    OutlinedTextField(
                        value = rapidLossTimeframeMinutes,
                        onValueChange = { rapidLossTimeframeMinutes = it },
                        label = { Text("Rapid Loss Timeframe (minutes)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                    OutlinedTextField(
                        value = circuitBreakerCooldownMinutes,
                        onValueChange = { circuitBreakerCooldownMinutes = it },
                        label = { Text("Circuit Breaker Cooldown (minutes)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                }
                
                HorizontalDivider()
                
                // Advanced Settings
                Text(
                    text = "Advanced Settings",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Volatility-Based Sizing")
                    Switch(
                        checked = volatilityBasedSizingEnabled,
                        onCheckedChange = { volatilityBasedSizingEnabled = it },
                        enabled = !isLoading
                    )
                }
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Performance-Based Adjustment")
                    Switch(
                        checked = performanceBasedAdjustmentEnabled,
                        onCheckedChange = { performanceBasedAdjustmentEnabled = it },
                        enabled = !isLoading
                    )
                }
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Kelly Criterion")
                    Switch(
                        checked = kellyCriterionEnabled,
                        onCheckedChange = { kellyCriterionEnabled = it },
                        enabled = !isLoading
                    )
                }
                
                if (kellyCriterionEnabled) {
                    OutlinedTextField(
                        value = kellyFraction,
                        onValueChange = { kellyFraction = it },
                        label = { Text("Kelly Fraction (%)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                }
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Correlation Limits")
                    Switch(
                        checked = correlationLimitsEnabled,
                        onCheckedChange = { correlationLimitsEnabled = it },
                        enabled = !isLoading
                    )
                }
                
                if (correlationLimitsEnabled) {
                    OutlinedTextField(
                        value = maxCorrelationExposurePct,
                        onValueChange = { maxCorrelationExposurePct = it },
                        label = { Text("Max Correlation Exposure (%)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                }
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Margin Call Protection")
                    Switch(
                        checked = marginCallProtectionEnabled,
                        onCheckedChange = { marginCallProtectionEnabled = it },
                        enabled = !isLoading
                    )
                }
                
                if (marginCallProtectionEnabled) {
                    OutlinedTextField(
                        value = minMarginRatio,
                        onValueChange = { minMarginRatio = it },
                        label = { Text("Min Margin Ratio (%)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                }
                
                OutlinedTextField(
                    value = maxTradesPerDayPerStrategy,
                    onValueChange = { maxTradesPerDayPerStrategy = it },
                    label = { Text("Max Trades/Day Per Strategy") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                
                OutlinedTextField(
                    value = maxTradesPerDayTotal,
                    onValueChange = { maxTradesPerDayTotal = it },
                    label = { Text("Max Trades/Day Total") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Auto-Reduce Order Size")
                    Switch(
                        checked = autoReduceOrderSize,
                        onCheckedChange = { autoReduceOrderSize = it },
                        enabled = !isLoading
                    )
                }
                
                if (isLoading) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Center
                    ) {
                        CircularProgressIndicator(modifier = Modifier.padding(Spacing.Medium))
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { 
                    if (!isEdit) {
                        if (selectedAccountId == null) {
                            accountError = "Account selection is required"
                            return@TextButton
                        }
                        accountError = null
                    }
                    onSave(createUpdatedConfig()) 
                },
                enabled = !isLoading && (isEdit || selectedAccountId != null)
            ) {
                Text("Save")
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isLoading
            ) {
                Text("Cancel")
            }
        }
    )
}
