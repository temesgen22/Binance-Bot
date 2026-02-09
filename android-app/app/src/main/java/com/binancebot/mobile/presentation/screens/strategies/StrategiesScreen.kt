@file:OptIn(ExperimentalMaterial3Api::class)

package com.binancebot.mobile.presentation.screens.strategies

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
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
    var showEditDialog by remember { mutableStateOf<String?>(null) }
    
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
                        // Overall Performance Summary
                        performanceList?.summary?.let { summary ->
                            OverallPerformanceSummary(summary = summary)
                        }
                        
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
                                
                                // Advanced Filters
                                AnimatedVisibility(
                                    visible = showAdvancedFilters,
                                    enter = expandVertically(),
                                    exit = shrinkVertically()
                                ) {
                                    Column(
                                        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                                    ) {
                                        // Symbol Filter
                                        OutlinedTextField(
                                            value = filterSymbol,
                                            onValueChange = { filterSymbol = it },
                                            modifier = Modifier.fillMaxWidth(),
                                            label = { Text("Symbol (e.g., BTCUSDT)") },
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
                                                label = { Text("Start Date (ISO)") },
                                                placeholder = { Text("YYYY-MM-DDTHH:mm:ss") },
                                                singleLine = true
                                            )
                                            OutlinedTextField(
                                                value = endDate ?: "",
                                                onValueChange = { endDate = it.takeIf { it.isNotBlank() } },
                                                modifier = Modifier.weight(1f),
                                                label = { Text("End Date (ISO)") },
                                                placeholder = { Text("YYYY-MM-DDTHH:mm:ss") },
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
                                        onEdit = { showEditDialog = performance.strategyId },
                                        onDelete = { showDeleteDialog = performance.strategyId },
                                        onDetails = { navController.navigate("strategy_details/${performance.strategyId}") }
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
fun OverallPerformanceSummary(summary: Map<String, Any>) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = Spacing.ScreenPadding, vertical = Spacing.Small),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.padding(Spacing.CardPadding)
        ) {
            Text(
                text = "Overall Performance",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(bottom = Spacing.Small)
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                StatCard(
                    label = "Total PnL",
                    value = FormatUtils.formatCurrency((summary["total_pnl"] as? Number)?.toDouble() ?: 0.0),
                    isPositive = (summary["total_pnl"] as? Number)?.toDouble() ?: 0.0 >= 0,
                    modifier = Modifier.weight(1f)
                )
                StatCard(
                    label = "Total Strategies",
                    value = "${summary["total_strategies"] ?: 0}",
                    modifier = Modifier.weight(1f)
                )
                StatCard(
                    label = "Active",
                    value = "${summary["active_strategies"] ?: 0}",
                    modifier = Modifier.weight(1f)
                )
            }
            Spacer(modifier = Modifier.height(Spacing.Small))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                StatCard(
                    label = "Win Rate",
                    value = String.format("%.2f%%", (summary["overall_win_rate"] as? Number)?.toDouble() ?: 0.0),
                    modifier = Modifier.weight(1f)
                )
                StatCard(
                    label = "Total Trades",
                    value = "${summary["total_trades"] ?: 0}",
                    modifier = Modifier.weight(1f)
                )
                StatCard(
                    label = "Best Strategy",
                    value = (summary["best_performing"] as? String) ?: "-",
                    isSmall = true,
                    modifier = Modifier.weight(1f)
                )
            }
        }
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
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    onDetails: () -> Unit
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
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Rank Badge
                    RankBadge(rank = performance.rank ?: 0)
                    
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = performance.strategyName,
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = "${performance.symbol} • ${performance.strategyType}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    StatusBadge(status = performance.status)
                    IconButton(onClick = onExpandToggle) {
                        Icon(
                            if (isExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                            contentDescription = if (isExpanded) "Collapse" else "Expand"
                        )
                    }
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
                performance.percentile?.let {
                    PercentileBadge(percentile = it)
                }
            }
            
            // Expanded Details
            AnimatedVisibility(
                visible = isExpanded,
                enter = expandVertically(),
                exit = shrinkVertically()
            ) {
                StrategyDetailsView(performance = performance)
            }
            
            Divider(modifier = Modifier.padding(vertical = Spacing.Small))
            
            // Actions
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                if (performance.status == "running") {
                    Button(
                        onClick = onStop,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.error
                        )
                    ) {
                        Icon(Icons.Default.Stop, null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        Text("Stop")
                    }
                } else {
                    Button(
                        onClick = onStart,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.primary
                        )
                    ) {
                        Icon(Icons.Default.PlayArrow, null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        Text("Start")
                    }
                }
                IconButton(onClick = onEdit) {
                    Icon(Icons.Default.Edit, "Edit", tint = MaterialTheme.colorScheme.primary)
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
fun StrategyDetailsView(performance: StrategyPerformanceDto) {
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
