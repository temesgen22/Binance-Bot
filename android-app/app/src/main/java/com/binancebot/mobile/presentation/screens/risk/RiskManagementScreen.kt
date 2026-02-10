package com.binancebot.mobile.presentation.screens.risk

import androidx.compose.foundation.layout.*
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
    
    // Auto-refresh
    LaunchedEffect(autoRefresh, selectedAccountId) {
        if (autoRefresh) {
            while (autoRefresh) {
                kotlinx.coroutines.delay(30000) // 30 seconds
                if (!autoRefresh) break
                viewModel.refresh(selectedAccountId)
            }
        }
    }
    
    LaunchedEffect(Unit) {
        viewModel.refresh(selectedAccountId)
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
                            Icon(Icons.Default.Refresh, contentDescription = "Refresh")
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
                    onClick = { selectedTabIndex = 0 },
                    text = { Text("Status") }
                )
                Tab(
                    selected = selectedTabIndex == 1,
                    onClick = { selectedTabIndex = 1 },
                    text = { Text("Portfolio Metrics") }
                )
                Tab(
                    selected = selectedTabIndex == 2,
                    onClick = { selectedTabIndex = 2 },
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
                    uiState = uiState,
                    onRetry = { viewModel.loadPortfolioRiskStatus(selectedAccountId) }
                )
                1 -> PortfolioMetricsTab(
                    portfolioMetrics = portfolioMetrics,
                    uiState = uiState,
                    onRetry = { viewModel.loadPortfolioMetrics(selectedAccountId) }
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

@Composable
private fun AccountSelector(
    selectedAccountId: String?,
    onAccountSelected: (String?) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Small),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "Account:",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold
            )
            Row(
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                FilterChip(
                    selected = selectedAccountId == null,
                    onClick = { onAccountSelected(null) },
                    label = { Text("All") }
                )
                FilterChip(
                    selected = selectedAccountId == "default",
                    onClick = { onAccountSelected("default") },
                    label = { Text("Default") }
                )
            }
        }
    }
}

// Portfolio Status Tab (Enhanced)
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
                    // Status Card
                    StatusCard(status = status)
                    
                    // Key Metrics Grid
                    MetricsGridCard(status = status)
                    
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
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Portfolio Risk Status",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold
                )
                Surface(
                    shape = MaterialTheme.shapes.medium,
                    color = MaterialTheme.colorScheme.surface
                ) {
                    Text(
                        text = (status.status ?: "Unknown").replaceFirstChar { it.uppercase() },
                        modifier = Modifier.padding(horizontal = Spacing.Medium, vertical = Spacing.Small),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            
            if (status.accountId != null) {
                Text(
                    text = "Account: ${status.accountId}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun MetricsGridCard(status: com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto) {
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
            
            // Metrics Grid
            Column(
                verticalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    MetricCard(
                        label = "Total Exposure",
                        value = status.totalExposure?.let { FormatUtils.formatCurrency(it) } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        label = "Daily PnL",
                        value = status.dailyPnL?.let { 
                            FormatUtils.formatCurrency(it)
                        } ?: "N/A",
                        valueColor = status.dailyPnL?.let {
                            if (it >= 0) MaterialTheme.colorScheme.primary 
                            else MaterialTheme.colorScheme.error
                        },
                        modifier = Modifier.weight(1f)
                    )
                }
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    MetricCard(
                        label = "Weekly PnL",
                        value = status.weeklyPnL?.let { 
                            FormatUtils.formatCurrency(it)
                        } ?: "N/A",
                        valueColor = status.weeklyPnL?.let {
                            if (it >= 0) MaterialTheme.colorScheme.primary 
                            else MaterialTheme.colorScheme.error
                        },
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        label = "Max Drawdown",
                        value = status.maxDrawdownPct?.let { 
                            "${String.format("%.2f", it * 100)}%"
                        } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                }
                
                status.currentDrawdownPct?.let {
                    MetricRow("Current Drawdown", "${String.format("%.2f", it * 100)}%")
                }
                status.dailyPnLPct?.let {
                    MetricRow("Daily PnL %", "${String.format("%.2f", it * 100)}%")
                }
                status.weeklyPnLPct?.let {
                    MetricRow("Weekly PnL %", "${String.format("%.2f", it * 100)}%")
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
                portfolioMetrics?.let { metrics ->
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
                            
                            metrics.totalBalanceUsdt?.let {
                                MetricRow("Total Balance", FormatUtils.formatCurrency(it))
                            }
                            metrics.availableBalanceUsdt?.let {
                                MetricRow("Available Balance", FormatUtils.formatCurrency(it))
                            }
                            metrics.usedMarginUsdt?.let {
                                MetricRow("Used Margin", FormatUtils.formatCurrency(it))
                            }
                            metrics.peakBalanceUsdt?.let {
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
                            metrics.winRate?.let {
                                MetricRow("Win Rate", "${String.format("%.2f", it * 100)}%")
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
                } ?: run {
                    EmptyStateCard(message = "No portfolio metrics available")
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
    LaunchedEffect(Unit) {
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
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(Spacing.ScreenPadding),
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                if (strategyMetrics.isEmpty()) {
                    EmptyStateCard(message = "No strategy metrics available")
                } else {
                    strategyMetrics.forEach { strategyMetric ->
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
                        text = strategyMetric.strategyName ?: strategyMetric.strategyId,
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
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    MetricCard(
                        label = "Trades",
                        value = metrics.totalTrades?.toString() ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        label = "Win Rate",
                        value = metrics.winRate?.let { 
                            "${String.format("%.2f", it * 100)}%"
                        } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                }
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    MetricCard(
                        label = "PnL",
                        value = (metrics.dailyPnLUsdt ?: metrics.weeklyPnLUsdt)?.let {
                            FormatUtils.formatCurrency(it)
                        } ?: "N/A",
                        valueColor = (metrics.dailyPnLUsdt ?: metrics.weeklyPnLUsdt)?.let {
                            if (it >= 0) MaterialTheme.colorScheme.primary 
                            else MaterialTheme.colorScheme.error
                        },
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        label = "Drawdown",
                        value = metrics.maxDrawdownPct?.let {
                            "${String.format("%.2f", it * 100)}%"
                        } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                }
                
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
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(Spacing.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
    ) {
        // Filters
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
                    EmptyStateCard(message = "No enforcement events found")
                } else {
                    enforcementHistory?.events?.forEach { event ->
                        EnforcementEventCard(event = event)
                    }
                    
                    // Pagination
                    if (enforcementHistory != null && enforcementHistory.total > pageSize) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
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
    var selectedReport by remember { mutableStateOf<com.binancebot.mobile.data.remote.dto.RiskReportDto?>(null) }
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
                modifier = Modifier.weight(1f)
            ) {
                Text("Daily Report")
            }
            Button(
                onClick = {
                    reportType = "weekly"
                    viewModel.loadWeeklyReport(accountId)
                },
                modifier = Modifier.weight(1f)
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
                    RiskReportCard(report = report, reportType = reportType ?: "")
                } else {
                    EmptyStateCard(message = "Select a report type to view")
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
            report.winRate?.let {
                MetricRow("Win Rate", "${String.format("%.2f", it * 100)}%")
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
            report.maxDrawdownPct?.let {
                MetricRow("Max Drawdown", "${String.format("%.2f", it * 100)}%")
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

// Configuration Tab (Enhanced - will continue in next part due to size)
@Composable
fun ConfigurationTab(
    riskConfig: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?,
    onRetry: () -> Unit,
    viewModel: RiskManagementViewModel,
    accountId: String?
) {
    var showEditDialog by remember { mutableStateOf(false) }
    val uiState by viewModel.uiState.collectAsState()
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(Spacing.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
    ) {
        riskConfig?.let { config ->
            // Portfolio Limits Section
            ConfigurationSection(
                title = "Portfolio Limits",
                items = listOf(
                    config.maxPortfolioExposureUsdt?.let { "Max Portfolio Exposure: ${FormatUtils.formatCurrency(it)}" },
                    config.maxPortfolioExposurePct?.let { "Max Portfolio Exposure: ${String.format("%.2f", it * 100)}%" },
                    config.maxDailyLossUsdt?.let { "Max Daily Loss: ${FormatUtils.formatCurrency(it)}" },
                    config.maxDailyLossPct?.let { "Max Daily Loss: ${String.format("%.2f", it * 100)}%" },
                    config.maxWeeklyLossUsdt?.let { "Max Weekly Loss: ${FormatUtils.formatCurrency(it)}" },
                    config.maxWeeklyLossPct?.let { "Max Weekly Loss: ${String.format("%.2f", it * 100)}%" },
                    config.maxDrawdownPct?.let { "Max Drawdown: ${String.format("%.2f", it * 100)}%" }
                ).filterNotNull()
            )
            
            // Circuit Breaker Section
            if (config.circuitBreakerEnabled) {
                ConfigurationSection(
                    title = "Circuit Breaker Settings",
                    items = listOf(
                        "Enabled: Yes",
                        config.maxConsecutiveLosses?.let { "Max Consecutive Losses: $it" },
                        config.rapidLossThresholdPct?.let { "Rapid Loss Threshold: ${String.format("%.2f", it * 100)}%" },
                        config.rapidLossTimeframeMinutes?.let { "Rapid Loss Timeframe: $it minutes" },
                        config.circuitBreakerCooldownMinutes?.let { "Cooldown: $it minutes" }
                    ).filterNotNull()
                )
            }
            
            // Advanced Settings
            val advancedSettings = mutableListOf<String>()
            if (config.volatilityBasedSizingEnabled) advancedSettings.add("Volatility-Based Sizing: Enabled")
            if (config.performanceBasedAdjustmentEnabled) advancedSettings.add("Performance-Based Adjustment: Enabled")
            if (config.kellyCriterionEnabled) {
                advancedSettings.add("Kelly Criterion: Enabled")
                config.kellyFraction?.let { advancedSettings.add("Kelly Fraction: ${String.format("%.2f", it * 100)}%") }
            }
            if (config.correlationLimitsEnabled) {
                advancedSettings.add("Correlation Limits: Enabled")
                config.maxCorrelationExposurePct?.let { advancedSettings.add("Max Correlation Exposure: ${String.format("%.2f", it * 100)}%") }
            }
            if (config.marginCallProtectionEnabled) {
                advancedSettings.add("Margin Call Protection: Enabled")
                config.minMarginRatio?.let { advancedSettings.add("Min Margin Ratio: ${String.format("%.2f", it * 100)}%") }
            }
            if (advancedSettings.isNotEmpty()) {
                ConfigurationSection(
                    title = "Advanced Settings",
                    items = advancedSettings
                )
            }
            
            Button(
                onClick = { showEditDialog = true },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Edit Configuration")
            }
        } ?: run {
            EmptyStateCard(message = "No risk configuration found")
            Button(
                onClick = { showEditDialog = true },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Create Configuration")
            }
        }
    }
    
    // Show loading/error states
    when (uiState) {
        is RiskManagementUiState.Success -> {
            LaunchedEffect(Unit) {
                showEditDialog = false
                viewModel.loadRiskConfig(accountId)
            }
        }
        else -> {}
    }
    
    // Edit/Create Configuration Dialog
    if (showEditDialog) {
        EditRiskConfigDialog(
            config = riskConfig,
            isEdit = riskConfig != null,
            isLoading = uiState is RiskManagementUiState.Loading,
            errorMessage = (uiState as? RiskManagementUiState.Error)?.message,
            onDismiss = { showEditDialog = false },
            onSave = { updatedConfig ->
                if (riskConfig != null) {
                    viewModel.updateRiskConfig(accountId, updatedConfig)
                } else {
                    viewModel.createRiskConfig(accountId, updatedConfig)
                }
            }
        )
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
private fun StrategyRiskConfigDialog(
    strategyId: String,
    strategyName: String?,
    onDismiss: () -> Unit,
    viewModel: RiskManagementViewModel
) {
    // This would show strategy-level risk configuration
    // Implementation would be similar to EditRiskConfigDialog but for strategy
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Strategy Risk Config: ${strategyName ?: strategyId}") },
        text = {
            Text("Strategy-level risk configuration will be implemented here.")
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text("Close")
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
    onSave: (com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto) -> Unit
) {
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
        return com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto(
            id = config?.id,
            accountId = config?.accountId,
            maxPortfolioExposureUsdt = maxPortfolioExposureUsdt.toDoubleOrNull(),
            maxPortfolioExposurePct = maxPortfolioExposurePct.toDoubleOrNull()?.div(100),
            maxDailyLossUsdt = maxDailyLossUsdt.toDoubleOrNull(),
            maxDailyLossPct = maxDailyLossPct.toDoubleOrNull()?.div(100),
            maxWeeklyLossUsdt = maxWeeklyLossUsdt.toDoubleOrNull(),
            maxWeeklyLossPct = maxWeeklyLossPct.toDoubleOrNull()?.div(100),
            maxDrawdownPct = maxDrawdownPct.toDoubleOrNull()?.div(100),
            dailyLossResetTime = dailyLossResetTime,
            weeklyLossResetDay = weeklyLossResetDay.toIntOrNull(),
            timezone = timezone,
            circuitBreakerEnabled = circuitBreakerEnabled,
            maxConsecutiveLosses = maxConsecutiveLosses.toIntOrNull(),
            rapidLossThresholdPct = rapidLossThresholdPct.toDoubleOrNull()?.div(100),
            rapidLossTimeframeMinutes = rapidLossTimeframeMinutes.toIntOrNull(),
            circuitBreakerCooldownMinutes = circuitBreakerCooldownMinutes.toIntOrNull(),
            volatilityBasedSizingEnabled = volatilityBasedSizingEnabled,
            performanceBasedAdjustmentEnabled = performanceBasedAdjustmentEnabled,
            kellyCriterionEnabled = kellyCriterionEnabled,
            kellyFraction = kellyFraction.toDoubleOrNull()?.div(100),
            correlationLimitsEnabled = correlationLimitsEnabled,
            maxCorrelationExposurePct = maxCorrelationExposurePct.toDoubleOrNull()?.div(100),
            marginCallProtectionEnabled = marginCallProtectionEnabled,
            minMarginRatio = minMarginRatio.toDoubleOrNull()?.div(100),
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
                onClick = { onSave(createUpdatedConfig()) },
                enabled = !isLoading
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
