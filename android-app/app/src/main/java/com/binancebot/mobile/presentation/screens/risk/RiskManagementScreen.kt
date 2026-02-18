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
// PortfolioMetricsTab -> RiskMetricsTab.kt; StrategyMetricsTab, StrategyRiskMetricCard -> RiskStrategyMetricsTab.kt;
// EnforcementHistoryTab, EnforcementEventCard -> RiskEnforcementTab.kt; ReportsTab, RiskReportCard -> RiskReportsTab.kt;
// ConfigurationTab, AccountConfigCard, ConfigurationSection -> RiskConfigurationTab.kt;
// StrategyRiskConfigDialog, StrategyRiskConfigDialogWithCallbacks, EditRiskConfigDialog, MetricRow, formatTimestamp -> RiskDialogs.kt (P1.1)

