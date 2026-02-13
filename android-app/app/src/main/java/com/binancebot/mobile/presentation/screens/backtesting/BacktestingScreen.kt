@file:OptIn(ExperimentalMaterial3Api::class)

package com.binancebot.mobile.presentation.screens.backtesting

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.BacktestStrategyDefaults
import com.binancebot.mobile.presentation.viewmodel.BacktestingViewModel
import com.binancebot.mobile.presentation.viewmodel.BacktestingUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BacktestingScreen(
    navController: NavController,
    viewModel: BacktestingViewModel = hiltViewModel()
) {
    var selectedTabIndex by remember { mutableStateOf(0) }
    val backtestHistory by viewModel.backtestHistory.collectAsState()
    val currentResult by viewModel.currentBacktestResult.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Backtesting") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
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
                    onClick = { 
                        selectedTabIndex = 0
                        viewModel.clearCurrentResult()
                    },
                    text = { Text("New") }
                )
                Tab(
                    selected = selectedTabIndex == 1,
                    onClick = { 
                        selectedTabIndex = 1
                        // Don't clear result if viewing details
                    },
                    text = { Text("History") }
                )
            }
            
            // Tab Content
            when (selectedTabIndex) {
                0 -> NewBacktestTab(
                    viewModel = viewModel,
                    uiState = uiState,
                    onRetry = { viewModel.loadBacktestHistory() }
                )
                1 -> {
                    // Show results if viewing a specific backtest
                    if (currentResult != null) {
                        Column(
                            modifier = Modifier
                                .fillMaxSize()
                                .verticalScroll(rememberScrollState())
                                .padding(Spacing.ScreenPadding),
                            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "Backtest Details",
                                    style = MaterialTheme.typography.titleLarge,
                                    fontWeight = FontWeight.Bold
                                )
                                TextButton(onClick = { viewModel.clearCurrentResult() }) {
                                    Text("Back to History")
                                }
                            }
                            BacktestResultsCard(
                                result = currentResult!!,
                                onDismiss = { viewModel.clearCurrentResult() }
                            )
                        }
                    } else {
                        BacktestHistoryTab(
                            backtestHistory = backtestHistory,
                            uiState = uiState,
                            onRetry = { viewModel.loadBacktestHistory() },
                            onViewDetails = { backtestId ->
                                // Show backtest details - find the backtest in history and display it
                                val backtest = backtestHistory.find { it.id == backtestId }
                                backtest?.let {
                                    // Store the result to display it
                                    viewModel.setCurrentResult(it)
                                }
                            }
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun NewBacktestTab(
    viewModel: BacktestingViewModel,
    uiState: BacktestingUiState,
    onRetry: () -> Unit = {}
) {
    val currentResult by viewModel.currentBacktestResult.collectAsState()
    
    var selectedStrategyType by remember { mutableStateOf<String?>(null) }
    var symbol by remember { mutableStateOf("BTCUSDT") }
    var startDate by remember { mutableStateOf("") }
    var endDate by remember { mutableStateOf("") }
    var leverage by remember { mutableStateOf("5") }
    var riskPerTrade by remember { mutableStateOf("0.01") }
    var initialBalance by remember { mutableStateOf("1000.0") }
    var showAdvancedOptions by remember { mutableStateOf(false) }
    var expandedStrategyTypeDropdown by remember { mutableStateOf(false) }
    var showDatePicker by remember { mutableStateOf(false) }
    
    LaunchedEffect(Unit) {
        viewModel.loadBacktestHistory()
    }
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(Spacing.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
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
                    text = "Backtest Configuration",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                HorizontalDivider()
                
                // Symbol Input
                OutlinedTextField(
                    value = symbol,
                    onValueChange = { symbol = it.uppercase() },
                    label = { Text("Symbol (e.g., BTCUSDT)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    leadingIcon = {
                        Icon(Icons.Default.CurrencyBitcoin, contentDescription = null)
                    }
                )
                
                // Strategy Type Selection (same options as web app)
                Text(
                    text = "Strategy Type",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = Spacing.Small)
                )
                ExposedDropdownMenuBox(
                    expanded = expandedStrategyTypeDropdown,
                    onExpandedChange = { expandedStrategyTypeDropdown = !expandedStrategyTypeDropdown }
                ) {
                    OutlinedTextField(
                        value = selectedStrategyType?.let { type ->
                            BacktestStrategyDefaults.STRATEGY_TYPES.find { it.first == type }?.second ?: type
                        } ?: "",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Select Strategy Type") },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        trailingIcon = {
                            ExposedDropdownMenuDefaults.TrailingIcon(expanded = expandedStrategyTypeDropdown)
                        },
                        placeholder = { Text("Choose a strategy type to backtest") }
                    )
                    ExposedDropdownMenu(
                        expanded = expandedStrategyTypeDropdown,
                        onDismissRequest = { expandedStrategyTypeDropdown = false }
                    ) {
                        BacktestStrategyDefaults.STRATEGY_TYPES.forEach { (type, displayName) ->
                            DropdownMenuItem(
                                text = { Text(displayName) },
                                onClick = {
                                    selectedStrategyType = type
                                    expandedStrategyTypeDropdown = false
                                }
                            )
                        }
                    }
                }
                
                // Date Range
                Text(
                    text = "Date Range",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = Spacing.Small)
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    OutlinedTextField(
                        value = startDate,
                        onValueChange = { startDate = it },
                        label = { Text("Start Date") },
                        placeholder = { Text("YYYY-MM-DD") },
                        modifier = Modifier.weight(1f),
                        trailingIcon = {
                            IconButton(onClick = { showDatePicker = true }) {
                                Icon(Icons.Default.DateRange, contentDescription = "Pick Date")
                            }
                        }
                    )
                    OutlinedTextField(
                        value = endDate,
                        onValueChange = { endDate = it },
                        label = { Text("End Date") },
                        placeholder = { Text("YYYY-MM-DD") },
                        modifier = Modifier.weight(1f),
                        trailingIcon = {
                            IconButton(onClick = { showDatePicker = true }) {
                                Icon(Icons.Default.DateRange, contentDescription = "Pick Date")
                            }
                        }
                    )
                }
                
                // Advanced Options Toggle
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Advanced Options",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Switch(
                        checked = showAdvancedOptions,
                        onCheckedChange = { showAdvancedOptions = it }
                    )
                }
                
                // Advanced Options
                if (showAdvancedOptions) {
                    Column(
                        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                        ) {
                            OutlinedTextField(
                                value = leverage,
                                onValueChange = { leverage = it },
                                label = { Text("Leverage") },
                                modifier = Modifier.weight(1f),
                                singleLine = true
                            )
                            OutlinedTextField(
                                value = riskPerTrade,
                                onValueChange = { riskPerTrade = it },
                                label = { Text("Risk Per Trade") },
                                modifier = Modifier.weight(1f),
                                singleLine = true
                            )
                        }
                        OutlinedTextField(
                            value = initialBalance,
                            onValueChange = { initialBalance = it },
                            label = { Text("Initial Balance (USDT)") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true
                        )
                    }
                }
                
                // Run Backtest Button
                Spacer(modifier = Modifier.height(Spacing.Medium))
                Button(
                    onClick = {
                        selectedStrategyType?.let { strategyType ->
                            viewModel.runBacktest(
                                symbol = symbol,
                                strategyType = strategyType,
                                startTime = startDate,
                                endTime = endDate,
                                leverage = leverage.toIntOrNull() ?: 5,
                                riskPerTrade = riskPerTrade.toDoubleOrNull() ?: 0.01,
                                initialBalance = initialBalance.toDoubleOrNull() ?: 1000.0,
                                params = BacktestStrategyDefaults.getDefaultParams(strategyType)
                            )
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = selectedStrategyType != null &&
                             symbol.isNotBlank() &&
                             startDate.isNotBlank() &&
                             endDate.isNotBlank() &&
                             uiState !is BacktestingUiState.Loading
                ) {
                    if (uiState is BacktestingUiState.Loading) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            strokeWidth = 2.dp
                        )
                        Spacer(modifier = Modifier.width(Spacing.Small))
                        Text("Running Backtest...")
                    } else {
                        Icon(Icons.Default.PlayArrow, contentDescription = null)
                        Spacer(modifier = Modifier.width(Spacing.Small))
                        Text("Run Backtest")
                    }
                }
            }
        }
        
        // Results Display
        currentResult?.let { result ->
            BacktestResultsCard(
                result = result,
                onDismiss = { viewModel.clearCurrentResult() }
            )
        }
        
        // Info Card
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.primaryContainer
            )
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(Spacing.Medium),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    Icons.Default.Info,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onPrimaryContainer
                )
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text(
                    text = "Backtesting allows you to test strategies on historical data to evaluate performance before live trading.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
            }
        }
    }
}

@Composable
fun BacktestResultsCard(
    result: com.binancebot.mobile.data.remote.dto.BacktestResultDto,
    onDismiss: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
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
                    text = "📊 Backtest Results",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                IconButton(onClick = onDismiss) {
                    Icon(Icons.Default.Close, contentDescription = "Close")
                }
            }
            HorizontalDivider()
            
            // Key Metrics
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text(
                        text = "Total PnL",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = com.binancebot.mobile.presentation.util.FormatUtils.formatCurrency(result.totalPnL),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = if (result.totalPnL >= 0) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.error
                        }
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = "Return",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = String.format("%.2f%%", result.totalReturnPct),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (result.totalReturnPct >= 0) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.error
                        }
                    )
                }
            }
            
            // Performance Metrics Grid
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant
                )
            ) {
                Column(
                    modifier = Modifier.padding(Spacing.Medium),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Win Rate",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = String.format("%.2f%%", result.winRate * 100),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Total Trades",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "${result.totalTrades} (${result.completedTrades} completed, ${result.openTrades} open)",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Winning/Losing",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "${result.winningTrades}W / ${result.losingTrades}L",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Avg Profit/Trade",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = com.binancebot.mobile.presentation.util.FormatUtils.formatCurrency(result.avgProfitPerTrade),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Largest Win",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = com.binancebot.mobile.presentation.util.FormatUtils.formatCurrency(result.largestWin),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Largest Loss",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = com.binancebot.mobile.presentation.util.FormatUtils.formatCurrency(result.largestLoss),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.error
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Max Drawdown",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "${com.binancebot.mobile.presentation.util.FormatUtils.formatCurrency(result.maxDrawdown)} (${String.format("%.2f%%", result.maxDrawdownPct)})",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.error
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Total Fees",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = com.binancebot.mobile.presentation.util.FormatUtils.formatCurrency(result.totalFees),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Final Balance",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = com.binancebot.mobile.presentation.util.FormatUtils.formatCurrency(result.finalBalance),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun BacktestHistoryTab(
    backtestHistory: List<com.binancebot.mobile.data.remote.dto.BacktestResultDto>,
    uiState: BacktestingUiState,
    onRetry: () -> Unit,
    onViewDetails: (String) -> Unit
) {
    when (uiState) {
        is BacktestingUiState.Loading -> {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        }
        is BacktestingUiState.Error -> {
            ErrorHandler(
                message = uiState.message,
                onRetry = onRetry,
                modifier = Modifier.fillMaxSize()
            )
        }
        else -> {
            if (backtestHistory.isEmpty()) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Icon(
                            Icons.Default.History,
                            contentDescription = "No history",
                            modifier = Modifier.size(64.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(Spacing.Medium))
                        Text(
                            text = "No backtest history",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(Spacing.Small))
                        Text(
                            text = "Run your first backtest to see results here",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            } else {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState())
                        .padding(Spacing.ScreenPadding),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    backtestHistory.forEach { backtest ->
                        BacktestHistoryCard(
                            backtest = backtest,
                            onClick = { onViewDetails(backtest.id) }
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun BacktestHistoryCard(
    backtest: com.binancebot.mobile.data.remote.dto.BacktestResultDto,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
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
                Text(
                    text = backtest.strategyName ?: "Unknown Strategy",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "#${backtest.id}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text(
                        text = "Date Range",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = "${backtest.startDate} - ${backtest.endDate}",
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = "Total PnL",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = com.binancebot.mobile.presentation.util.FormatUtils.formatCurrency(backtest.totalPnL),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (backtest.totalPnL >= 0) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.error
                        }
                    )
                }
            }
            
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "Win Rate: ${String.format("%.1f%%", backtest.winRate * 100)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    text = "Trades: ${backtest.totalTrades}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

