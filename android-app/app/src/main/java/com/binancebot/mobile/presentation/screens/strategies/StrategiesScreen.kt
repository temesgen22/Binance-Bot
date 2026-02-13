@file:OptIn(ExperimentalMaterial3Api::class)

package com.binancebot.mobile.presentation.screens.strategies

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import android.util.Log
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.components.StatusBadge
import com.binancebot.mobile.presentation.components.BottomNavigationBar
import com.binancebot.mobile.presentation.components.shouldShowBottomNav
import com.binancebot.mobile.presentation.components.SwipeRefreshBox
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.StrategyPerformanceViewModel
import com.binancebot.mobile.presentation.viewmodel.StrategyPerformanceUiState
import com.binancebot.mobile.presentation.viewmodel.StrategiesViewModel
import com.binancebot.mobile.presentation.viewmodel.AccountViewModel
import com.binancebot.mobile.presentation.viewmodel.RiskManagementUiState
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StrategiesScreen(
    navController: NavController,
    performanceViewModel: StrategyPerformanceViewModel = hiltViewModel(),
    strategiesViewModel: StrategiesViewModel = hiltViewModel(),
    accountViewModel: AccountViewModel = hiltViewModel()
) {
    val performanceList by performanceViewModel.performanceList.collectAsState()
    val performanceUiState by performanceViewModel.uiState.collectAsState()
    val accounts by accountViewModel.accounts.collectAsState()
    val actionInProgress by strategiesViewModel.actionInProgress.collectAsState()
    val currentRoute = navController.currentDestination?.route
    
    // Filter and search state
    var searchQuery by remember { mutableStateOf("") }
    var filterStatus by remember { mutableStateOf<String?>(null) }
    var filterAccount by remember { mutableStateOf<String?>(null) }
    var filterSymbol by remember { mutableStateOf("") }
    var rankBy by remember { mutableStateOf("total_pnl") }
    var showFilters by remember { mutableStateOf(false) }
    var showAdvancedFilters by remember { mutableStateOf(false) }
    var expandedStrategyId by remember { mutableStateOf<String?>(null) }
    var showDeleteDialog by remember { mutableStateOf<String?>(null) }
    
    // Date filters
    var startDate by remember { mutableStateOf<String?>(null) }
    var endDate by remember { mutableStateOf<String?>(null) }
    
    // Load accounts on first load
    LaunchedEffect(Unit) {
        accountViewModel.loadAccounts()
    }
    
    // Load performance data when filters change
    LaunchedEffect(searchQuery, filterStatus, filterAccount, filterSymbol, rankBy, startDate, endDate) {
        performanceViewModel.loadPerformance(
            strategyName = searchQuery.takeIf { it.isNotBlank() },
            symbol = filterSymbol.takeIf { it.isNotBlank() },
            status = filterStatus,
            rankBy = rankBy,
            startDate = startDate,
            endDate = endDate,
            accountId = filterAccount
        )
    }
    
    // After start/stop success, refresh performance list so Start/Stop button updates
    val refreshPerformanceTrigger by strategiesViewModel.refreshPerformanceTrigger.collectAsState()
    LaunchedEffect(refreshPerformanceTrigger) {
        if (refreshPerformanceTrigger > 0) {
            performanceViewModel.loadPerformance(
                strategyName = searchQuery.takeIf { it.isNotBlank() },
                symbol = filterSymbol.takeIf { it.isNotBlank() },
                status = filterStatus,
                rankBy = rankBy,
                startDate = startDate,
                endDate = endDate,
                accountId = filterAccount
            )
        }
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Strategy Performance") },
                actions = {
                    IconButton(onClick = { showFilters = !showFilters }) {
                        Icon(
                            Icons.Default.FilterList,
                            contentDescription = "Filter",
                            tint = if (filterStatus != null || filterAccount != null || filterSymbol.isNotBlank()) 
                                MaterialTheme.colorScheme.primary 
                            else 
                                MaterialTheme.colorScheme.onSurface
                        )
                    }
                    IconButton(onClick = { 
                        performanceViewModel.loadPerformance(
                            strategyName = searchQuery.takeIf { it.isNotBlank() },
                            symbol = filterSymbol.takeIf { it.isNotBlank() },
                            status = filterStatus,
                            rankBy = rankBy,
                            startDate = startDate,
                            endDate = endDate,
                            accountId = filterAccount
                        )
                    }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                }
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { navController.navigate("create_strategy") }
            ) {
                Icon(Icons.Default.Add, contentDescription = "Add Strategy")
            }
        },
        bottomBar = {
            if (shouldShowBottomNav(currentRoute)) {
                BottomNavigationBar(
                    currentRoute = currentRoute,
                    onNavigate = { route ->
                        navController.navigate(route) {
                            popUpTo(Screen.Home.route) { inclusive = false }
                            launchSingleTop = true
                        }
                    }
                )
            }
        }
    ) { padding ->
        when (performanceUiState) {
            is StrategyPerformanceUiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
            is StrategyPerformanceUiState.Error -> {
                ErrorHandler(
                    message = (performanceUiState as StrategyPerformanceUiState.Error).message,
                    onRetry = { 
                        performanceViewModel.loadPerformance(
                            strategyName = searchQuery.takeIf { it.isNotBlank() },
                            symbol = filterSymbol.takeIf { it.isNotBlank() },
                            status = filterStatus,
                            rankBy = rankBy,
                            startDate = startDate,
                            endDate = endDate,
                            accountId = filterAccount
                        )
                    },
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                )
            }
            else -> {
                SwipeRefreshBox(
                    isRefreshing = false,
                    onRefresh = { 
                        performanceViewModel.loadPerformance(
                            strategyName = searchQuery.takeIf { it.isNotBlank() },
                            symbol = filterSymbol.takeIf { it.isNotBlank() },
                            status = filterStatus,
                            rankBy = rankBy,
                            startDate = startDate,
                            endDate = endDate,
                            accountId = filterAccount
                        )
                    }
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding)
                    ) {
                        // Search Bar
                        OutlinedTextField(
                            value = searchQuery,
                            onValueChange = { searchQuery = it },
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = Spacing.ScreenPadding, vertical = Spacing.Small),
                            placeholder = { Text("Search strategies...") },
                            leadingIcon = {
                                Icon(Icons.Default.Search, contentDescription = "Search")
                            },
                            trailingIcon = {
                                if (searchQuery.isNotEmpty()) {
                                    IconButton(onClick = { searchQuery = "" }) {
                                        Icon(Icons.Default.Clear, contentDescription = "Clear")
                                    }
                                }
                            },
                            singleLine = true
                        )
                        
                        // Filters Section
                        AnimatedVisibility(
                            visible = showFilters,
                            enter = expandVertically(),
                            exit = shrinkVertically()
                        ) {
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = Spacing.ScreenPadding)
                            ) {
                                // Basic Filters
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                                ) {
                                    FilterChip(
                                        selected = filterStatus == null,
                                        onClick = { filterStatus = null },
                                        label = { Text("All") }
                                    )
                                    FilterChip(
                                        selected = filterStatus == "running",
                                        onClick = { filterStatus = if (filterStatus == "running") null else "running" },
                                        label = { Text("Running") }
                                    )
                                    FilterChip(
                                        selected = filterStatus == "stopped",
                                        onClick = { filterStatus = if (filterStatus == "stopped") null else "stopped" },
                                        label = { Text("Stopped") }
                                    )
                                    FilterChip(
                                        selected = filterStatus == "stopped_by_risk",
                                        onClick = { filterStatus = if (filterStatus == "stopped_by_risk") null else "stopped_by_risk" },
                                        label = { Text("Stopped by Risk") }
                                    )
                                    FilterChip(
                                        selected = filterStatus == "error",
                                        onClick = { filterStatus = if (filterStatus == "error") null else "error" },
                                        label = { Text("Error") }
                                    )
                                }
                                
                                Spacer(modifier = Modifier.height(Spacing.Small))
                                
                                // Advanced Filters Toggle
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = "Advanced Filters",
                                        style = MaterialTheme.typography.titleSmall
                                    )
                                    IconButton(onClick = { showAdvancedFilters = !showAdvancedFilters }) {
                                        Icon(
                                            if (showAdvancedFilters) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                                            contentDescription = "Toggle Advanced Filters"
                                        )
                                    }
                                }
                                
                                // Advanced Filters - Compact and Scrollable
                                AnimatedVisibility(
                                    visible = showAdvancedFilters,
                                    enter = expandVertically(),
                                    exit = shrinkVertically()
                                ) {
                                    Card(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .heightIn(max = 300.dp), // Limit max height
                                        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                                    ) {
                                        Column(
                                            modifier = Modifier
                                                .verticalScroll(rememberScrollState())
                                                .padding(Spacing.Small),
                                            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                                        ) {
                                            // Symbol Filter
                                            OutlinedTextField(
                                                value = filterSymbol,
                                                onValueChange = { filterSymbol = it },
                                                modifier = Modifier.fillMaxWidth(),
                                                label = { Text("Symbol") },
                                                singleLine = true
                                            )
                                            
                                            // Account Filter
                                            AccountFilterDropdown(
                                                accounts = accounts,
                                                selectedAccountId = filterAccount,
                                                onAccountSelected = { filterAccount = it }
                                            )
                                            
                                            // Rank By Selector
                                            RankBySelector(
                                                selectedRankBy = rankBy,
                                                onRankBySelected = { rankBy = it }
                                            )
                                            
                                            // Date Range Filters
                                            Row(
                                                modifier = Modifier.fillMaxWidth(),
                                                horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                                            ) {
                                                OutlinedTextField(
                                                    value = startDate ?: "",
                                                    onValueChange = { startDate = it.takeIf { it.isNotBlank() } },
                                                    modifier = Modifier.weight(1f),
                                                    label = { Text("Start") },
                                                    placeholder = { Text("YYYY-MM-DD") },
                                                    singleLine = true
                                                )
                                                OutlinedTextField(
                                                    value = endDate ?: "",
                                                    onValueChange = { endDate = it.takeIf { it.isNotBlank() } },
                                                    modifier = Modifier.weight(1f),
                                                    label = { Text("End") },
                                                    placeholder = { Text("YYYY-MM-DD") },
                                                    singleLine = true
                                                )
                                            }
                                            
                                            // Clear Filters Button
                                            TextButton(
                                                onClick = {
                                                    filterStatus = null
                                                    filterAccount = null
                                                    filterSymbol = ""
                                                    rankBy = "total_pnl"
                                                    startDate = null
                                                    endDate = null
                                                },
                                                modifier = Modifier.fillMaxWidth()
                                            ) {
                                                Text("Clear All Filters")
                                            }
                                        }
                                    }
                                }
                                
                                Spacer(modifier = Modifier.height(Spacing.Small))
                            }
                        }
                        
                        // Strategies List
                        val strategies = performanceList?.strategies ?: emptyList()
                        if (strategies.isEmpty()) {
                            Box(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .weight(1f),
                                contentAlignment = Alignment.Center
                            ) {
                                Column(
                                    horizontalAlignment = Alignment.CenterHorizontally
                                ) {
                                    Icon(
                                        Icons.Default.SearchOff,
                                        contentDescription = "No results",
                                        modifier = Modifier.size(64.dp),
                                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Spacer(modifier = Modifier.height(Spacing.Medium))
                                    Text(
                                        text = "No strategies found",
                                        style = MaterialTheme.typography.titleMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        } else {
                            LazyColumn(
                                modifier = Modifier.weight(1f),
                                contentPadding = PaddingValues(Spacing.ScreenPadding),
                                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                            ) {
                                items(
                                    items = strategies,
                                    key = { it.strategyId }
                                ) { performance ->
                                    EnhancedStrategyCard(
                                        performance = performance,
                                        isExpanded = expandedStrategyId == performance.strategyId,
                                        onExpandToggle = { 
                                            expandedStrategyId = if (expandedStrategyId == performance.strategyId) null else performance.strategyId
                                        },
                                        onStart = { strategiesViewModel.startStrategy(performance.strategyId) },
                                        onStop = { strategiesViewModel.stopStrategy(performance.strategyId) },
                                        onCopy = {
                                            strategiesViewModel.setStrategyToCopy(performance)
                                            navController.navigate("create_strategy")
                                        },
                                        onDelete = { showDeleteDialog = performance.strategyId },
                                        onDetails = { navController.navigate("strategy_details/${performance.strategyId}") },
                                        strategiesViewModel = strategiesViewModel,
                                        isActionLoading = performance.strategyId in actionInProgress
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    // Delete Confirmation Dialog
    showDeleteDialog?.let { strategyId ->
        AlertDialog(
            onDismissRequest = { showDeleteDialog = null },
            title = { Text("Delete Strategy") },
            text = { Text("Are you sure you want to delete this strategy? This action cannot be undone.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        strategiesViewModel.deleteStrategy(strategyId)
                        showDeleteDialog = null
                    }
                ) {
                    Text("Delete", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = null }) {
                    Text("Cancel")
                }
            }
        )
    }
}

@Composable
fun StatCard(
    label: String,
    value: String,
    isPositive: Boolean = false,
    isSmall: Boolean = false,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(modifier = Modifier.height(Spacing.Tiny))
        Text(
            text = value,
            style = if (isSmall) MaterialTheme.typography.bodySmall else MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = if (isPositive && !isSmall) {
                if (value.startsWith("-")) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary
            } else {
                MaterialTheme.colorScheme.onSurface
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountFilterDropdown(
    accounts: List<com.binancebot.mobile.domain.model.Account>,
    selectedAccountId: String?,
    onAccountSelected: (String?) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    
    ExposedDropdownMenuBox(
        expanded = expanded,
        onExpandedChange = { expanded = it }
    ) {
        OutlinedTextField(
            value = accounts.find { it.accountId == selectedAccountId }?.name ?: "All Accounts",
            onValueChange = {},
            readOnly = true,
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor(),
            label = { Text("Account") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) }
        )
        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false }
        ) {
            DropdownMenuItem(
                text = { Text("All Accounts") },
                onClick = {
                    onAccountSelected(null)
                    expanded = false
                }
            )
            accounts.forEach { account ->
                DropdownMenuItem(
                    text = { 
                        Text("${account.name} (${account.accountId})${if (account.testnet) " [TESTNET]" else ""}")
                    },
                    onClick = {
                        onAccountSelected(account.accountId)
                        expanded = false
                    }
                )
            }
        }
    }
}

@Composable
fun RankBySelector(
    selectedRankBy: String,
    onRankBySelected: (String) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    
    val rankOptions = listOf(
        "total_pnl" to "Total PnL",
        "win_rate" to "Win Rate",
        "completed_trades" to "Completed Trades",
        "realized_pnl" to "Realized PnL",
        "unrealized_pnl" to "Unrealized PnL"
    )
    
    ExposedDropdownMenuBox(
        expanded = expanded,
        onExpandedChange = { expanded = it }
    ) {
        OutlinedTextField(
            value = rankOptions.find { it.first == selectedRankBy }?.second ?: "Total PnL",
            onValueChange = {},
            readOnly = true,
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor(),
            label = { Text("Rank By") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) }
        )
        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false }
        ) {
            rankOptions.forEach { (value, label) ->
                DropdownMenuItem(
                    text = { Text(label) },
                    onClick = {
                        onRankBySelected(value)
                        expanded = false
                    }
                )
            }
        }
    }
}

@Composable
fun EnhancedStrategyCard(
    performance: StrategyPerformanceDto,
    isExpanded: Boolean,
    onExpandToggle: () -> Unit,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onCopy: () -> Unit,
    onDelete: () -> Unit,
    onDetails: () -> Unit,
    strategiesViewModel: StrategiesViewModel,
    isActionLoading: Boolean = false
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
            // Header with Rank
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(onClick = onDetails),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.weight(1f)
                ) {
                    // Rank Badge
                    RankBadge(rank = performance.rank ?: 0)
                    
                    Column(
                        modifier = Modifier
                            .weight(1f)
                            .padding(end = Spacing.Small)
                    ) {
                        Text(
                            text = performance.strategyName,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                            lineHeight = MaterialTheme.typography.titleMedium.lineHeight * 0.9
                        )
                        Spacer(modifier = Modifier.height(2.dp))
                        Text(
                            text = "${performance.symbol} • ${performance.strategyType}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
                
                // Right side: Status, Health Indicator, Expand button
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Tiny),
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.wrapContentWidth()
                ) {
                    StatusBadge(status = performance.status)
                    // Health indicator for running strategies - always visible next to status
                    val isRunning = performance.status.lowercase().trim() == "running"
                    if (isRunning) {
                        Spacer(modifier = Modifier.width(4.dp))
                        StrategyHealthIndicator(
                            strategyId = performance.strategyId,
                            strategiesViewModel = strategiesViewModel
                        )
                    }
                }
                IconButton(onClick = onExpandToggle) {
                    Icon(
                        if (isExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = if (isExpanded) "Collapse" else "Expand"
                    )
                }
            }
            
            // Key Metrics Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                MetricColumn("Total PnL", FormatUtils.formatCurrency(performance.totalPnl), performance.totalPnl >= 0)
                MetricColumn("Win Rate", "${String.format("%.2f", performance.winRate)}%")
                MetricColumn("Trades", "${performance.completedTrades}/${performance.totalTrades}")
            }
            
            // Second Metrics Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                MetricColumn("Realized", FormatUtils.formatCurrency(performance.totalRealizedPnl), performance.totalRealizedPnl >= 0)
                MetricColumn("Unrealized", FormatUtils.formatCurrency(performance.totalUnrealizedPnl), performance.totalUnrealizedPnl >= 0)
                performance.percentile?.let {
                    PercentileBadge(percentile = it)
                }
            }
            
            // Position Info (if has position)
            if (performance.positionSide != null && performance.positionSize != null && performance.positionSize > 0) {
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Default.ShowChart,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp),
                            tint = MaterialTheme.colorScheme.primary
                        )
                        Text(
                            text = "${performance.positionSide} • ${String.format("%.4f", performance.positionSize)}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.primary,
                            fontWeight = FontWeight.Medium
                        )
                    }
                    performance.totalUnrealizedPnl?.let { pnl ->
                        Text(
                            text = FormatUtils.formatCurrency(pnl),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            color = if (pnl >= 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                        )
                    }
                }
            }
            
            // Expanded Details
            AnimatedVisibility(
                visible = isExpanded,
                enter = expandVertically(),
                exit = shrinkVertically()
            ) {
                val riskManagementViewModel: com.binancebot.mobile.presentation.viewmodel.RiskManagementViewModel = androidx.hilt.navigation.compose.hiltViewModel()
                StrategyDetailsView(
                    performance = performance,
                    riskManagementViewModel = riskManagementViewModel,
                    strategiesViewModel = strategiesViewModel
                )
            }
            
            Divider(modifier = Modifier.padding(vertical = Spacing.Small))
            
            // Actions
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                // Only show Start button if not stopped_by_risk (user can't start if stopped by risk)
                if (performance.status == "running") {
                    Button(
                        onClick = onStop,
                        modifier = Modifier.weight(1f),
                        enabled = !isActionLoading,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.error
                        )
                    ) {
                        if (isActionLoading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                color = MaterialTheme.colorScheme.onError,
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        } else {
                            Icon(Icons.Default.Stop, null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        }
                        Text(if (isActionLoading) "Stopping..." else "Stop")
                    }
                } else if (performance.status != "stopped_by_risk") {
                    Button(
                        onClick = onStart,
                        modifier = Modifier.weight(1f),
                        enabled = !isActionLoading,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.primary
                        )
                    ) {
                        if (isActionLoading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                color = MaterialTheme.colorScheme.onPrimary,
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        } else {
                            Icon(Icons.Default.PlayArrow, null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        }
                        Text(if (isActionLoading) "Starting..." else "Start")
                    }
                } else {
                    // Show disabled button for stopped_by_risk
                    Button(
                        onClick = { },
                        modifier = Modifier.weight(1f),
                        enabled = false,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        )
                    ) {
                        Icon(Icons.Default.Warning, null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        Text("Stopped by Risk")
                    }
                }
                IconButton(onClick = onCopy) {
                    Icon(Icons.Default.ContentCopy, "Copy", tint = MaterialTheme.colorScheme.primary)
                }
                IconButton(onClick = onDelete) {
                    Icon(Icons.Default.Delete, "Delete", tint = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}

@Composable
fun RankBadge(rank: Int) {
    val (backgroundColor, textColor) = when (rank) {
        1 -> Pair(Color(0xFFFFD700), Color(0xFF333333)) // Gold
        2 -> Pair(Color(0xFFC0C0C0), Color(0xFF333333)) // Silver
        3 -> Pair(Color(0xFFCD7F32), Color.White) // Bronze
        else -> Pair(MaterialTheme.colorScheme.surfaceVariant, MaterialTheme.colorScheme.onSurfaceVariant)
    }
    
    Surface(
        modifier = Modifier.size(40.dp),
        shape = MaterialTheme.shapes.medium,
        color = backgroundColor
    ) {
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier.fillMaxSize()
        ) {
            Text(
                text = "$rank",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = textColor
            )
        }
    }
}

@Composable
fun PercentileBadge(percentile: Double) {
    val (backgroundColor, textColor) = when {
        percentile >= 75 -> Pair(
            MaterialTheme.colorScheme.primaryContainer,
            MaterialTheme.colorScheme.onPrimaryContainer
        )
        percentile >= 50 -> Pair(
            MaterialTheme.colorScheme.secondaryContainer,
            MaterialTheme.colorScheme.onSecondaryContainer
        )
        else -> Pair(
            MaterialTheme.colorScheme.errorContainer,
            MaterialTheme.colorScheme.onErrorContainer
        )
    }
    
    Surface(
        shape = MaterialTheme.shapes.small,
        color = backgroundColor
    ) {
        Text(
            text = "${percentile.toInt()}%",
            style = MaterialTheme.typography.labelSmall,
            color = textColor,
            modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny)
        )
    }
}

@Composable
fun MetricColumn(label: String, value: String, isPositive: Boolean = false) {
    Column {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Bold,
            color = if (isPositive && value.startsWith("-").not()) {
                MaterialTheme.colorScheme.primary
            } else if (value.startsWith("-")) {
                MaterialTheme.colorScheme.error
            } else {
                MaterialTheme.colorScheme.onSurface
            }
        )
    }
}

@Composable
fun StrategyDetailsView(
    performance: StrategyPerformanceDto,
    riskManagementViewModel: com.binancebot.mobile.presentation.viewmodel.RiskManagementViewModel,
    strategiesViewModel: StrategiesViewModel
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = Spacing.Small),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
    ) {
        // Performance Metrics
        DetailSection("Performance Metrics") {
            DetailRow("Total Trades", "${performance.totalTrades}")
            DetailRow("Completed Trades", "${performance.completedTrades}")
            DetailRow("Winning Trades", "${performance.winningTrades}", isPositive = true)
            DetailRow("Losing Trades", "${performance.losingTrades}", isPositive = false)
            DetailRow("Avg Profit/Trade", FormatUtils.formatCurrency(performance.avgProfitPerTrade))
            DetailRow("Largest Win", FormatUtils.formatCurrency(performance.largestWin), isPositive = true)
            DetailRow("Largest Loss", FormatUtils.formatCurrency(performance.largestLoss), isPositive = false)
            DetailRow("Realized PnL", FormatUtils.formatCurrency(performance.totalRealizedPnl), performance.totalRealizedPnl >= 0)
            DetailRow("Unrealized PnL", FormatUtils.formatCurrency(performance.totalUnrealizedPnl), performance.totalUnrealizedPnl >= 0)
        }
        
        // Current Position
        if (performance.positionSide != null && performance.positionSize != null && performance.positionSize > 0) {
            DetailSection("Current Position") {
                DetailRow("Position Side", performance.positionSide)
                DetailRow("Position Size", "${String.format("%.4f", performance.positionSize)}")
                performance.entryPrice?.let {
                    DetailRow("Entry Price", FormatUtils.formatCurrency(it))
                }
                performance.currentPrice?.let {
                    DetailRow("Current Price", FormatUtils.formatCurrency(it))
                }
                DetailRow("Unrealized PnL", FormatUtils.formatCurrency(performance.totalUnrealizedPnl), performance.totalUnrealizedPnl >= 0)
            }
        }
        
        // Strategy Configuration
        DetailSection("Strategy Configuration") {
            DetailRow("Strategy Type", performance.strategyType)
            performance.accountId?.let {
                DetailRow("Account", it)
            }
            DetailRow("Leverage", "${performance.leverage}x")
            DetailRow("Risk per Trade", "${String.format("%.2f", performance.riskPerTrade * 100)}%")
            performance.fixedAmount?.let {
                DetailRow("Fixed Amount", FormatUtils.formatCurrency(it))
            }
        }
        
        // Strategy Parameters
        if (performance.params.isNotEmpty()) {
            DetailSection("Strategy Parameters") {
                val relevantParams = getRelevantParamsForStrategy(performance.strategyType, performance.params)
                relevantParams.forEach { (key, value) ->
                    DetailRow(
                        key.replace("_", " ").replaceFirstChar { it.uppercase() },
                        formatParamValueForDisplay(value)
                    )
                }
            }
        }
        
        // Timestamps
        DetailSection("Timestamps") {
            DetailRow("Created", FormatUtils.formatDateTime(performance.createdAt))
            performance.startedAt?.let {
                DetailRow("Last Started", FormatUtils.formatDateTime(it))
            }
            performance.stoppedAt?.let {
                DetailRow("Last Stopped", FormatUtils.formatDateTime(it))
            }
            performance.lastTradeAt?.let {
                DetailRow("Last Trade", FormatUtils.formatDateTime(it))
            }
            performance.lastSignal?.let {
                DetailRow("Last Signal", it)
            }
        }
        
        // Auto-Tuning Status
        DetailSection("Auto-Tuning") {
            DetailRow("Status", if (performance.autoTuningEnabled) "Enabled" else "Disabled")
        }
        
        // Health Status Section (for running strategies)
        if (performance.status == "running") {
            StrategyHealthDetailsSection(
                strategyId = performance.strategyId,
                strategiesViewModel = strategiesViewModel
            )
        }
        
        // Risk Configuration Section
        StrategyRiskConfigSection(
            strategyId = performance.strategyId,
            strategyName = performance.strategyName,
            viewModel = riskManagementViewModel
        )
    }
}

fun getRelevantParamsForStrategy(strategyType: String, params: Map<String, Any>): Map<String, Any> {
    val emaScalpingParams = listOf(
        "ema_fast", "ema_slow", "take_profit_pct", "stop_loss_pct",
        "interval_seconds", "kline_interval", "enable_short",
        "min_ema_separation", "enable_htf_bias", "cooldown_candles",
        "trailing_stop_enabled", "trailing_stop_activation_pct"
    )
    
    val rangeMeanReversionParams = listOf(
        "lookback_period", "buy_zone_pct", "sell_zone_pct",
        "ema_fast_period", "ema_slow_period", "max_ema_spread_pct",
        "max_atr_multiplier", "rsi_period", "rsi_oversold",
        "rsi_overbought", "tp_buffer_pct", "sl_buffer_pct", "kline_interval"
    )
    
    val relevantKeys = when {
        strategyType == "scalping" || strategyType == "ema_crossover" || strategyType == "reverse_scalping" -> emaScalpingParams
        strategyType == "range_mean_reversion" -> rangeMeanReversionParams
        else -> params.keys.toList()
    }
    
    return params.filterKeys { it in relevantKeys }
}

fun formatParamValueForDisplay(value: Any?): String {
    return when (value) {
        is Boolean -> value.toString()
        is Double -> String.format(Locale.getDefault(), "%.4f", value)
        is Float -> String.format(Locale.getDefault(), "%.4f", value)
        is Number -> value.toString()
        null -> "N/A"
        else -> value.toString()
    }
}

@Composable
fun DetailSection(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f)
        )
    ) {
        Column(
            modifier = Modifier.padding(Spacing.Small),
            verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary
            )
            content()
        }
    }
}

@Composable
fun StrategyHealthIndicator(
    strategyId: String,
    strategiesViewModel: StrategiesViewModel
) {
    val strategyHealth by strategiesViewModel.strategyHealth.collectAsState()
    val health = strategyHealth[strategyId]
    var isLoading by remember(strategyId) { mutableStateOf(true) }
    
    // Load health status when component is displayed
    LaunchedEffect(strategyId) {
        // Always load health when component is displayed
        isLoading = true
        Log.d("StrategyHealth", "Loading health for strategy: $strategyId")
        strategiesViewModel.loadStrategyHealth(strategyId)
    }
    
    // Update loading state when health data changes
    LaunchedEffect(health) {
        if (health != null) {
            isLoading = false
            Log.d("StrategyHealth", "Health loaded for $strategyId: ${health.healthStatus}")
        }
    }
    
    // Timeout: if no health after delay, show default state
    LaunchedEffect(strategyId) {
        kotlinx.coroutines.delay(2000)
        if (health == null && isLoading) {
            isLoading = false
            Log.d("StrategyHealth", "No health data for $strategyId after timeout")
        }
    }
    
    // Always show indicator for running strategies
    val healthStatus = health?.healthStatus
    
    val icon: String
    val text: String
    val color: androidx.compose.ui.graphics.Color
    val bgColor: androidx.compose.ui.graphics.Color
    
    when {
        isLoading -> {
            icon = "⟳"
            text = "Loading"
            color = MaterialTheme.colorScheme.onSurfaceVariant
            bgColor = MaterialTheme.colorScheme.surfaceVariant
        }
        healthStatus == "execution_stale" -> {
            icon = "⚠"
            text = ""
            color = MaterialTheme.colorScheme.error
            bgColor = MaterialTheme.colorScheme.errorContainer
        }
        healthStatus == "task_dead" -> {
            icon = "✗"
            text = ""
            color = MaterialTheme.colorScheme.error
            bgColor = MaterialTheme.colorScheme.errorContainer
        }
        healthStatus == "no_execution_tracking" -> {
            icon = "?"
            text = ""
            color = MaterialTheme.colorScheme.onSurfaceVariant
            bgColor = MaterialTheme.colorScheme.surfaceVariant
        }
        healthStatus == "no_recent_orders" -> {
            icon = "⚠"
            text = ""
            color = MaterialTheme.colorScheme.errorContainer
            bgColor = MaterialTheme.colorScheme.onErrorContainer
        }
        healthStatus == "healthy" -> {
            icon = "✓"
            text = ""
            color = MaterialTheme.colorScheme.primary
            bgColor = MaterialTheme.colorScheme.primaryContainer
        }
        else -> {
            // Default: show indicator even if no data (assume healthy)
            icon = "✓"
            text = "OK"
            color = MaterialTheme.colorScheme.primary
            bgColor = MaterialTheme.colorScheme.primaryContainer
        }
    }
    
    // Simple icon-only health indicator - no border, no text, just colored icon
    Log.d("StrategyHealth", "Rendering icon for $strategyId: isLoading=$isLoading, healthStatus=$healthStatus, icon=$icon")
    
    Box(
        modifier = Modifier.size(24.dp),
        contentAlignment = Alignment.Center
    ) {
        if (isLoading) {
            CircularProgressIndicator(
                modifier = Modifier.size(20.dp),
                strokeWidth = 2.dp,
                color = color
            )
        } else {
            Text(
                text = icon,
                style = MaterialTheme.typography.titleMedium,
                color = color,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
fun StrategyHealthDetailsSection(
    strategyId: String,
    strategiesViewModel: StrategiesViewModel
) {
    val strategyHealth by strategiesViewModel.strategyHealth.collectAsState()
    val health = strategyHealth[strategyId]
    
    // Load health status when section is displayed
    LaunchedEffect(strategyId) {
        strategiesViewModel.loadStrategyHealth(strategyId)
    }
    
    DetailSection("Execution Health Status") {
        if (health != null) {
            val statusText = when (health.healthStatus) {
                "healthy" -> "✓ Healthy - Strategy is executing normally"
                "execution_stale" -> "⚠ Stale - Last execution was too long ago"
                "task_dead" -> "✗ Dead - Execution task has crashed"
                "no_execution_tracking" -> "? No Tracking - Execution tracking not available"
                "no_recent_orders" -> "⚠ No Orders - Strategy running but not placing orders"
                else -> "? Unknown Status"
            }
            
            DetailRow("Status", statusText)
            
            health.issues?.takeIf { it.isNotEmpty() }?.let { issues ->
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                Text(
                    text = "Issues:",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.error
                )
                issues.forEach { issue ->
                    Text(
                        text = "• $issue",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(start = Spacing.Medium, top = Spacing.Tiny)
                    )
                }
            }
            
            health.executionStatus?.let { execStatus ->
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                execStatus["last_execution_age_seconds"]?.let { ageSeconds ->
                    val ageMinutes = (ageSeconds as? Number)?.toDouble()?.div(60) ?: 0.0
                    DetailRow("Last Execution", "${String.format("%.1f", ageMinutes)} minutes ago")
                }
                execStatus["execution_stale"]?.let { stale ->
                    if (stale == true) {
                        DetailRow("Execution Status", "⚠ Stale", isPositive = false)
                    }
                }
            }
            
            health.taskStatus?.let { taskStatus ->
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                taskStatus["task_running"]?.let { running ->
                    DetailRow("Task Running", if (running == true) "Yes" else "No", isPositive = running == true)
                }
                taskStatus["task_done"]?.let { done ->
                    if (done == true) {
                        DetailRow("Task Status", "✗ Task has exited", isPositive = false)
                    }
                }
            }
        } else {
            DetailRow("Status", "Loading health status...")
        }
    }
}

@Composable
fun StrategyRiskConfigSection(
    strategyId: String,
    strategyName: String,
    viewModel: com.binancebot.mobile.presentation.viewmodel.RiskManagementViewModel
) {
    var showRiskConfigDialog by remember { mutableStateOf(false) }
    val strategyRiskConfig by viewModel.strategyRiskConfig.collectAsState()
    
    // Load risk config when section is displayed
    LaunchedEffect(strategyId) {
        viewModel.loadStrategyRiskConfig(strategyId)
    }
    
    val configExists = strategyRiskConfig != null
    
    val uiState by viewModel.uiState.collectAsState()
    var isLoadingConfig by remember(strategyId) { mutableStateOf(true) }
    
    // Track loading state
    LaunchedEffect(strategyId, uiState) {
        if (uiState is RiskManagementUiState.Loading) {
            isLoadingConfig = true
        } else {
            isLoadingConfig = false
        }
    }
    
    DetailSection("Strategy Level Risk Configuration") {
        if (isLoadingConfig) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center
            ) {
                CircularProgressIndicator(modifier = Modifier.size(24.dp))
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text(
                    text = "Loading risk configuration...",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else if (configExists) {
            strategyRiskConfig?.let { config ->
                DetailRow("Status", "Configured", isPositive = true)
                if (config.enabled == true) {
                    DetailRow("Enabled", "Yes", isPositive = true)
                }
                config.maxDailyLossUsdt?.let {
                    DetailRow("Max Daily Loss", FormatUtils.formatCurrency(it))
                }
                config.maxDailyLossPct?.let {
                    DetailRow("Max Daily Loss %", "${String.format("%.2f", it * 100)}%")
                }
                config.maxWeeklyLossUsdt?.let {
                    DetailRow("Max Weekly Loss", FormatUtils.formatCurrency(it))
                }
                config.maxWeeklyLossPct?.let {
                    DetailRow("Max Weekly Loss %", "${String.format("%.2f", it * 100)}%")
                }
                config.maxDrawdownPct?.let {
                    DetailRow("Max Drawdown", "${String.format("%.2f", it * 100)}%")
                }
            }
            Button(
                onClick = { showRiskConfigDialog = true },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            ) {
                Icon(Icons.Default.Edit, null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text("Edit Risk Config")
            }
        } else {
            DetailRow("Status", "Not Configured", isPositive = false)
            Text(
                text = "No custom risk configuration set. Using account-level limits.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(vertical = Spacing.Small)
            )
            Button(
                onClick = { showRiskConfigDialog = true },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.primary
                )
            ) {
                Icon(Icons.Default.Add, null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text("Configure Risk")
            }
        }
    }
    
    // Show risk config dialog
    if (showRiskConfigDialog) {
        // Use the same dialog from RiskManagementScreen
        com.binancebot.mobile.presentation.screens.risk.StrategyRiskConfigDialog(
            strategyId = strategyId,
            strategyName = strategyName,
            onDismiss = { showRiskConfigDialog = false },
            viewModel = viewModel
        )
    }
}

/**
 * Displays account-level risk configuration (read-only).
 * Used on Strategy Details to show the account limits that apply when no strategy-level config exists.
 */
@Composable
fun AccountRiskConfigSection(
    accountId: String,
    riskConfig: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?,
    isLoading: Boolean
) {
    DetailSection("Account Risk Configuration") {
        if (isLoading) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center
            ) {
                CircularProgressIndicator(modifier = Modifier.size(24.dp))
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text(
                    text = "Loading account risk configuration...",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else if (riskConfig != null) {
            DetailRow("Account", accountId)
            DetailRow("Status", "Configured", isPositive = true)
            riskConfig.maxPortfolioExposureUsdt?.let {
                DetailRow("Max Portfolio Exposure", FormatUtils.formatCurrency(it))
            }
            riskConfig.maxPortfolioExposurePct?.let {
                DetailRow("Max Portfolio Exposure %", "${String.format("%.2f", it)}%")
            }
            riskConfig.maxDailyLossUsdt?.let {
                DetailRow("Max Daily Loss", FormatUtils.formatCurrency(it))
            }
            riskConfig.maxDailyLossPct?.let {
                DetailRow("Max Daily Loss %", "${String.format("%.2f", if (it <= 1) it * 100 else it)}%")
            }
            riskConfig.maxWeeklyLossUsdt?.let {
                DetailRow("Max Weekly Loss", FormatUtils.formatCurrency(it))
            }
            riskConfig.maxWeeklyLossPct?.let {
                DetailRow("Max Weekly Loss %", "${String.format("%.2f", if (it <= 1) it * 100 else it)}%")
            }
            riskConfig.maxDrawdownPct?.let {
                DetailRow("Max Drawdown", "${String.format("%.2f", if (it <= 1) it * 100 else it)}%")
            }
            if (riskConfig.circuitBreakerEnabled) {
                DetailRow("Circuit Breaker", "Enabled", isPositive = true)
            }
        } else {
            DetailRow("Status", "Not Configured", isPositive = false)
            Text(
                text = "No risk configuration for this account. Strategy will use default behavior.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(vertical = Spacing.Small)
            )
        }
    }
}

@Composable
fun DetailRow(label: String, value: String, isPositive: Boolean? = null) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Medium,
            color = when {
                isPositive == true -> MaterialTheme.colorScheme.primary
                isPositive == false -> MaterialTheme.colorScheme.error
                else -> MaterialTheme.colorScheme.onSurface
            }
        )
    }
}
