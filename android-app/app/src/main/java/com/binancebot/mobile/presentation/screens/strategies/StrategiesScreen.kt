package com.binancebot.mobile.presentation.screens.strategies

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import com.binancebot.mobile.presentation.components.StatusBadge
import com.binancebot.mobile.presentation.components.BottomNavigationBar
import com.binancebot.mobile.presentation.components.shouldShowBottomNav
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.StrategiesViewModel
import com.binancebot.mobile.presentation.viewmodel.StrategiesUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StrategiesScreen(
    navController: NavController,
    viewModel: StrategiesViewModel = hiltViewModel()
) {
    val strategies by viewModel.strategies.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    val isRefreshing by viewModel.isRefreshing.collectAsState()
    val currentRoute = navController.currentDestination?.route
    
    var showDeleteDialog by remember { mutableStateOf<String?>(null) }
    var showEditDialog by remember { mutableStateOf<com.binancebot.mobile.domain.model.Strategy?>(null) }
    
    // Filter and search state
    var searchQuery by remember { mutableStateOf("") }
    var filterStatus by remember { mutableStateOf<String?>(null) }
    var showFilters by remember { mutableStateOf(false) }
    
    // Filtered strategies
    val filteredStrategies = remember(strategies, searchQuery, filterStatus) {
        strategies.filter { strategy ->
            val matchesSearch = searchQuery.isBlank() || 
                strategy.name.contains(searchQuery, ignoreCase = true) ||
                strategy.symbol.contains(searchQuery, ignoreCase = true) ||
                strategy.strategyType.contains(searchQuery, ignoreCase = true)
            val matchesFilter = filterStatus == null || strategy.status == filterStatus
            matchesSearch && matchesFilter
        }
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Strategies") },
                actions = {
                    IconButton(onClick = { showFilters = !showFilters }) {
                        Icon(
                            Icons.Default.FilterList,
                            contentDescription = "Filter",
                            tint = if (filterStatus != null) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface
                        )
                    }
                    IconButton(onClick = { viewModel.refreshStrategies() }) {
                        Icon(
                            Icons.Default.Refresh,
                            contentDescription = "Refresh",
                            tint = if (isRefreshing) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface
                        )
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
        when (uiState) {
            is StrategiesUiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
            is StrategiesUiState.Error -> {
                ErrorHandler(
                    message = (uiState as StrategiesUiState.Error).message,
                    onRetry = { viewModel.loadStrategies() },
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                )
            }
            else -> {
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
                    
                    // Filter Chips (when filters are shown)
                    if (showFilters) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = Spacing.ScreenPadding),
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
                    }
                    
                    // Strategies List
                    if (filteredStrategies.isEmpty()) {
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
                                    text = if (strategies.isEmpty()) "No strategies found" else "No matching strategies",
                                    style = MaterialTheme.typography.titleMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                if (strategies.isNotEmpty() && (searchQuery.isNotEmpty() || filterStatus != null)) {
                                    Spacer(modifier = Modifier.height(Spacing.Small))
                                    TextButton(onClick = { 
                                        searchQuery = ""
                                        filterStatus = null
                                    }) {
                                        Text("Clear filters")
                                    }
                                }
                            }
                        }
                    } else {
                        LazyColumn(
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(Spacing.ScreenPadding),
                            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                        ) {
                            items(
                                items = filteredStrategies,
                                key = { it.id }
                            ) { strategy ->
                                StrategyCard(
                                    strategy = strategy,
                                    onStart = { viewModel.startStrategy(strategy.id) },
                                    onStop = { viewModel.stopStrategy(strategy.id) },
                                    onEdit = { showEditDialog = strategy },
                                    onDelete = { showDeleteDialog = strategy.id },
                                    onDetails = { navController.navigate("strategy_details/${strategy.id}") }
                                )
                            }
                        }
                    }
                }
            }
        }
    }
    
    // Edit Strategy Dialog
    showEditDialog?.let { strategy ->
        EditStrategyDialog(
            strategy = strategy,
            onDismiss = { showEditDialog = null },
            onConfirm = { request ->
                viewModel.updateStrategy(strategy.id, request)
                showEditDialog = null
            }
        )
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
                        viewModel.deleteStrategy(strategyId)
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
fun StrategyCard(
    strategy: com.binancebot.mobile.domain.model.Strategy,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    onDetails: () -> Unit = {}
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
            // Header
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(onClick = onDetails),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = strategy.name,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "${strategy.symbol} • ${strategy.strategyType}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                StatusBadge(status = strategy.status)
            }
            
            // Metrics
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text(
                        text = "Leverage",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = "${strategy.leverage}x",
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
                strategy.riskPerTrade?.let {
                    Column {
                        Text(
                            text = "Risk/Trade",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "${String.format("%.2f", it * 100)}%",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
                strategy.unrealizedPnL?.let {
                    Column {
                        Text(
                            text = "Unrealized PnL",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = FormatUtils.formatCurrency(it),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            color = if (it >= 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                        )
                    }
                }
            }
            
            Divider(modifier = Modifier.padding(vertical = Spacing.Small))
            
            // Actions
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                if (strategy.isRunning) {
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
