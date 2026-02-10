@file:OptIn(ExperimentalMaterial3Api::class)

package com.binancebot.mobile.presentation.screens.walkforward

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
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.WalkForwardViewModel
import com.binancebot.mobile.presentation.viewmodel.WalkForwardUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WalkForwardScreen(
    navController: NavController,
    viewModel: WalkForwardViewModel = hiltViewModel()
) {
    var selectedTabIndex by remember { mutableStateOf(0) }
    val progress by viewModel.progress.collectAsState()
    val result by viewModel.result.collectAsState()
    val history by viewModel.history.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Walk-Forward Analysis") },
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
                    onClick = { selectedTabIndex = 0 },
                    text = { Text("New") }
                )
                Tab(
                    selected = selectedTabIndex == 1,
                    onClick = { selectedTabIndex = 1 },
                    text = { Text("Dashboard") }
                )
                Tab(
                    selected = selectedTabIndex == 2,
                    onClick = { selectedTabIndex = 2 },
                    text = { Text("History") }
                )
            }
            
            // Tab Content
            when (selectedTabIndex) {
                0 -> NewWalkForwardTab(
                    viewModel = viewModel,
                    uiState = uiState,
                    progress = progress,
                    result = result,
                    onRetry = { viewModel.loadHistory() }
                )
                1 -> WalkForwardDashboardTab(
                    viewModel = viewModel,
                    uiState = uiState,
                    progress = progress,
                    result = result
                )
                2 -> WalkForwardHistoryTab(
                    history = history,
                    uiState = uiState,
                    onRetry = { viewModel.loadHistory() },
                    onViewDetails = { taskId ->
                        viewModel.getResult(taskId)
                        selectedTabIndex = 1 // Switch to dashboard to show result
                    }
                )
            }
        }
    }
}

@Composable
fun NewWalkForwardTab(
    viewModel: WalkForwardViewModel,
    uiState: WalkForwardUiState,
    progress: com.binancebot.mobile.data.remote.dto.WalkForwardProgressDto?,
    result: com.binancebot.mobile.data.remote.dto.WalkForwardResultDto?,
    onRetry: () -> Unit = {}
) {
    val strategiesViewModel: com.binancebot.mobile.presentation.viewmodel.StrategiesViewModel = hiltViewModel()
    val strategies by strategiesViewModel.strategies.collectAsState()
    
    var selectedStrategy by remember { mutableStateOf<com.binancebot.mobile.domain.model.Strategy?>(null) }
    var symbol by remember { mutableStateOf("BTCUSDT") }
    var startDate by remember { mutableStateOf("") }
    var endDate by remember { mutableStateOf("") }
    var trainingPeriodDays by remember { mutableStateOf("30") }
    var testPeriodDays by remember { mutableStateOf("7") }
    var stepSizeDays by remember { mutableStateOf("7") }
    var windowType by remember { mutableStateOf("rolling") }
    var leverage by remember { mutableStateOf("5") }
    var riskPerTrade by remember { mutableStateOf("0.01") }
    var initialBalance by remember { mutableStateOf("1000.0") }
    var showAdvancedOptions by remember { mutableStateOf(false) }
    var expandedStrategyDropdown by remember { mutableStateOf(false) }
    var expandedWindowTypeDropdown by remember { mutableStateOf(false) }
    
    LaunchedEffect(Unit) {
        strategiesViewModel.loadStrategies()
        viewModel.loadHistory()
    }
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(Spacing.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
    ) {
        // Show progress if running
        if (uiState is WalkForwardUiState.Running && progress != null) {
            WalkForwardProgressCard(progress = progress)
        }
        
        // Show result if completed
        result?.let { res ->
            WalkForwardResultCard(
                result = res,
                onDismiss = { viewModel.clearCurrentResult() }
            )
        }
        
        // Configuration Card
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
                    text = "Walk-Forward Configuration",
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
                    enabled = uiState !is WalkForwardUiState.Running,
                    leadingIcon = {
                        Icon(Icons.Default.CurrencyBitcoin, contentDescription = null)
                    }
                )
                
                // Strategy Selection
                ExposedDropdownMenuBox(
                    expanded = expandedStrategyDropdown && uiState !is WalkForwardUiState.Running,
                    onExpandedChange = { 
                        if (uiState !is WalkForwardUiState.Running) {
                            expandedStrategyDropdown = !expandedStrategyDropdown
                        }
                    }
                ) {
                    OutlinedTextField(
                        value = selectedStrategy?.let { "${it.name} (${it.strategyType})" } ?: "",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Strategy Type") },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        enabled = uiState !is WalkForwardUiState.Running,
                        trailingIcon = {
                            ExposedDropdownMenuDefaults.TrailingIcon(expanded = expandedStrategyDropdown)
                        },
                        placeholder = { Text("Select strategy") }
                    )
                    ExposedDropdownMenu(
                        expanded = expandedStrategyDropdown,
                        onDismissRequest = { expandedStrategyDropdown = false }
                    ) {
                        strategies.forEach { strategy ->
                            DropdownMenuItem(
                                text = { Text("${strategy.name} (${strategy.strategyType})") },
                                onClick = {
                                    selectedStrategy = strategy
                                    symbol = strategy.symbol
                                    expandedStrategyDropdown = false
                                }
                            )
                        }
                    }
                }
                
                // Date Range
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
                        enabled = uiState !is WalkForwardUiState.Running
                    )
                    OutlinedTextField(
                        value = endDate,
                        onValueChange = { endDate = it },
                        label = { Text("End Date") },
                        placeholder = { Text("YYYY-MM-DD") },
                        modifier = Modifier.weight(1f),
                        enabled = uiState !is WalkForwardUiState.Running
                    )
                }
                
                // Walk-Forward Parameters
                Text(
                    text = "Walk-Forward Parameters",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = Spacing.Small)
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    OutlinedTextField(
                        value = trainingPeriodDays,
                        onValueChange = { trainingPeriodDays = it },
                        label = { Text("Training Days") },
                        modifier = Modifier.weight(1f),
                        enabled = uiState !is WalkForwardUiState.Running
                    )
                    OutlinedTextField(
                        value = testPeriodDays,
                        onValueChange = { testPeriodDays = it },
                        label = { Text("Test Days") },
                        modifier = Modifier.weight(1f),
                        enabled = uiState !is WalkForwardUiState.Running
                    )
                    OutlinedTextField(
                        value = stepSizeDays,
                        onValueChange = { stepSizeDays = it },
                        label = { Text("Step Days") },
                        modifier = Modifier.weight(1f),
                        enabled = uiState !is WalkForwardUiState.Running
                    )
                }
                
                // Window Type
                ExposedDropdownMenuBox(
                    expanded = expandedWindowTypeDropdown && uiState !is WalkForwardUiState.Running,
                    onExpandedChange = { 
                        if (uiState !is WalkForwardUiState.Running) {
                            expandedWindowTypeDropdown = !expandedWindowTypeDropdown
                        }
                    }
                ) {
                    OutlinedTextField(
                        value = windowType.replaceFirstChar { it.uppercase() },
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Window Type") },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        enabled = uiState !is WalkForwardUiState.Running,
                        trailingIcon = {
                            ExposedDropdownMenuDefaults.TrailingIcon(expanded = expandedWindowTypeDropdown)
                        }
                    )
                    ExposedDropdownMenu(
                        expanded = expandedWindowTypeDropdown,
                        onDismissRequest = { expandedWindowTypeDropdown = false }
                    ) {
                        DropdownMenuItem(
                            text = { Text("Rolling") },
                            onClick = {
                                windowType = "rolling"
                                expandedWindowTypeDropdown = false
                            }
                        )
                        DropdownMenuItem(
                            text = { Text("Expanding") },
                            onClick = {
                                windowType = "expanding"
                                expandedWindowTypeDropdown = false
                            }
                        )
                    }
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
                        onCheckedChange = { showAdvancedOptions = it },
                        enabled = uiState !is WalkForwardUiState.Running
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
                                enabled = uiState !is WalkForwardUiState.Running
                            )
                            OutlinedTextField(
                                value = riskPerTrade,
                                onValueChange = { riskPerTrade = it },
                                label = { Text("Risk Per Trade") },
                                modifier = Modifier.weight(1f),
                                enabled = uiState !is WalkForwardUiState.Running
                            )
                        }
                        OutlinedTextField(
                            value = initialBalance,
                            onValueChange = { initialBalance = it },
                            label = { Text("Initial Balance (USDT)") },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = uiState !is WalkForwardUiState.Running
                        )
                    }
                }
                
                // Start Button
                Spacer(modifier = Modifier.height(Spacing.Medium))
                Button(
                    onClick = {
                        selectedStrategy?.let { strategy ->
                            viewModel.startWalkForwardAnalysis(
                                symbol = symbol,
                                strategyType = strategy.strategyType,
                                startTime = startDate,
                                endTime = endDate,
                                trainingPeriodDays = trainingPeriodDays.toIntOrNull() ?: 30,
                                testPeriodDays = testPeriodDays.toIntOrNull() ?: 7,
                                stepSizeDays = stepSizeDays.toIntOrNull() ?: 7,
                                windowType = windowType,
                                leverage = leverage.toIntOrNull() ?: 5,
                                riskPerTrade = riskPerTrade.toDoubleOrNull() ?: 0.01,
                                initialBalance = initialBalance.toDoubleOrNull() ?: 1000.0,
                                params = emptyMap()
                            )
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = selectedStrategy != null && 
                             symbol.isNotBlank() && 
                             startDate.isNotBlank() && 
                             endDate.isNotBlank() && 
                             uiState !is WalkForwardUiState.Running &&
                             uiState !is WalkForwardUiState.Loading
                ) {
                    if (uiState is WalkForwardUiState.Loading || uiState is WalkForwardUiState.Running) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            strokeWidth = 2.dp
                        )
                        Spacer(modifier = Modifier.width(Spacing.Small))
                        Text("Starting...")
                    } else {
                        Icon(Icons.Default.PlayArrow, contentDescription = null)
                        Spacer(modifier = Modifier.width(Spacing.Small))
                        Text("Start Walk-Forward Analysis")
                    }
                }
                
                // Error Display
                if (uiState is WalkForwardUiState.Error) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        )
                    ) {
                        Text(
                            text = (uiState as WalkForwardUiState.Error).message,
                            modifier = Modifier.padding(Spacing.Medium),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                    }
                }
            }
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
                    text = "Walk-Forward Analysis helps validate that your strategy performs well on unseen data, reducing overfitting risk.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
            }
        }
    }
}

@Composable
fun WalkForwardDashboardTab(
    viewModel: WalkForwardViewModel,
    uiState: WalkForwardUiState,
    progress: com.binancebot.mobile.data.remote.dto.WalkForwardProgressDto?,
    result: com.binancebot.mobile.data.remote.dto.WalkForwardResultDto?
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(Spacing.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
    ) {
        // Progress Display
        if (uiState is WalkForwardUiState.Running && progress != null) {
            WalkForwardProgressCard(progress = progress)
        }
        
        // Result Display
        result?.let { res ->
            WalkForwardResultCard(
                result = res,
                onDismiss = { viewModel.clearCurrentResult() }
            )
        }
        
        // Empty State
        if (progress == null && result == null) {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Icon(
                        Icons.Default.Dashboard,
                        contentDescription = "No dashboard",
                        modifier = Modifier.size(64.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(Spacing.Medium))
                    Text(
                        text = "Walk-Forward Dashboard",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(Spacing.Small))
                    Text(
                        text = "Start a walk-forward analysis to see progress and results here",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

@Composable
fun WalkForwardHistoryTab(
    history: List<com.binancebot.mobile.data.remote.dto.WalkForwardHistoryItemDto>,
    uiState: WalkForwardUiState,
    onRetry: () -> Unit,
    onViewDetails: (String) -> Unit
) {
    when (uiState) {
        is WalkForwardUiState.Loading -> {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        }
        is WalkForwardUiState.Error -> {
            ErrorHandler(
                message = uiState.message,
                onRetry = onRetry,
                modifier = Modifier.fillMaxSize()
            )
        }
        else -> {
            if (history.isEmpty()) {
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
                            text = "No walk-forward history",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(Spacing.Small))
                        Text(
                            text = "Run your first walk-forward analysis to see results here",
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
                    history.forEach { item ->
                        WalkForwardHistoryCard(
                            item = item,
                            onClick = { 
                                item.taskId?.let { onViewDetails(it) }
                            }
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun WalkForwardProgressCard(
    progress: com.binancebot.mobile.data.remote.dto.WalkForwardProgressDto
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
                    text = "🔄 Analysis in Progress",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                Surface(
                    shape = MaterialTheme.shapes.small,
                    color = MaterialTheme.colorScheme.primary
                ) {
                    Text(
                        text = "${progress.currentWindow}/${progress.totalWindows}",
                        modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            
            // Progress Bar
            LinearProgressIndicator(
                progress = { (progress.progressPct / 100.0).toFloat() },
                modifier = Modifier.fillMaxWidth()
            )
            
            Text(
                text = String.format("%.1f%% Complete", progress.progressPct),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold
            )
            
            progress.message?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            
            progress.estimatedTimeRemainingSeconds?.let { seconds ->
                val minutes = seconds / 60
                Text(
                    text = "Estimated time remaining: ${minutes}m ${seconds % 60}s",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
fun WalkForwardResultCard(
    result: com.binancebot.mobile.data.remote.dto.WalkForwardResultDto,
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
                    text = "📊 Walk-Forward Results",
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
                        text = "Total Return",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = String.format("%.2f%%", result.totalReturnPct),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = if (result.totalReturnPct >= 0) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.error
                        }
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = "Consistency",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = String.format("%.1f%%", result.consistencyScore * 100),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            
            // Performance Metrics
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
                            text = "Avg Window Return",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = String.format("%.2f%%", result.avgWindowReturnPct),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Sharpe Ratio",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = String.format("%.2f", result.sharpeRatio),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold
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
                            text = String.format("%.2f%%", result.maxDrawdownPct),
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
                            text = "Total Trades",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "${result.totalTrades}",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Avg Win Rate",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = String.format("%.2f%%", result.avgWinRate * 100),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "Total Windows",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "${result.totalWindows}",
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
fun WalkForwardHistoryCard(
    item: com.binancebot.mobile.data.remote.dto.WalkForwardHistoryItemDto,
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
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = item.name ?: "${item.symbol} - ${item.strategyType}",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "${item.startTime.split("T")[0]} to ${item.endTime.split("T")[0]}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Surface(
                    shape = MaterialTheme.shapes.small,
                    color = when (item.status.lowercase()) {
                        "completed" -> MaterialTheme.colorScheme.primary
                        "running" -> MaterialTheme.colorScheme.secondary
                        "failed" -> MaterialTheme.colorScheme.error
                        else -> MaterialTheme.colorScheme.surfaceVariant
                    }
                ) {
                    Text(
                        text = item.status.replaceFirstChar { it.uppercase() },
                        modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "Windows: ${item.completedWindows ?: 0}/${item.totalWindows}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                item.totalReturnPct?.let {
                    Text(
                        text = String.format("Return: %.2f%%", it),
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.Bold,
                        color = if (it >= 0) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.error
                        }
                    )
                }
            }
        }
    }
}


