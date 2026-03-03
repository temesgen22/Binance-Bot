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
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.util.AppLogger
import com.binancebot.mobile.data.remote.dto.StrategyHealthDto
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
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StrategiesScreen(
    navController: NavController,
    performanceViewModel: StrategyPerformanceViewModel = hiltViewModel(),
    strategiesViewModel: StrategiesViewModel = hiltViewModel(),
    accountViewModel: AccountViewModel = hiltViewModel(),
    riskManagementViewModel: com.binancebot.mobile.presentation.viewmodel.RiskManagementViewModel = hiltViewModel()
) {
    val performanceList by performanceViewModel.performanceListWithLivePosition.collectAsState()
    val performanceUiState by performanceViewModel.uiState.collectAsState()
    val accounts by accountViewModel.accounts.collectAsState()
    val actionInProgress by strategiesViewModel.actionInProgress.collectAsState()
    val strategyRiskConfigs by riskManagementViewModel.strategyRiskConfigs.collectAsState()
    val loadingStrategyRiskId by riskManagementViewModel.loadingStrategyRiskId.collectAsState()
    val currentRoute = navController.currentDestination?.route
    
    // Filter and search state
    var searchQuery by remember { mutableStateOf("") }
    var debouncedSearchQuery by remember { mutableStateOf("") }
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
    
    // Debounce search query (e.g. 400ms) so loadPerformance isn't called on every keystroke
    LaunchedEffect(searchQuery) {
        delay(400)
        debouncedSearchQuery = searchQuery
    }
    
    // Load accounts on first load
    LaunchedEffect(Unit) {
        accountViewModel.loadAccounts()
    }
    
    // Load performance data when filters change (uses debounced search)
    LaunchedEffect(debouncedSearchQuery, filterStatus, filterAccount, filterSymbol, rankBy, startDate, endDate) {
        performanceViewModel.loadPerformance(
            strategyName = debouncedSearchQuery.takeIf { it.isNotBlank() },
            symbol = filterSymbol.takeIf { it.isNotBlank() },
            status = filterStatus,
            rankBy = rankBy,
            startDate = startDate,
            endDate = endDate,
            accountId = filterAccount
        )
    }
    
    // On start/stop success, update only that strategy's status in the list (single card refresh)
    LaunchedEffect(Unit) {
        strategiesViewModel.strategyStatusUpdate.collect { (strategyId, status) ->
            performanceViewModel.updateStrategyStatus(strategyId, status)
        }
    }
    LaunchedEffect(Unit) {
        strategiesViewModel.strategyRemoved.collect { strategyId ->
            performanceViewModel.removeStrategy(strategyId)
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
                            StrategyPerformanceFilterPanel(
                                filterStatus = filterStatus,
                                onFilterStatusChange = { filterStatus = it },
                                filterAccount = filterAccount,
                                onFilterAccountChange = { filterAccount = it },
                                filterSymbol = filterSymbol,
                                onFilterSymbolChange = { filterSymbol = it },
                                rankBy = rankBy,
                                onRankByChange = { rankBy = it },
                                startDate = startDate,
                                onStartDateChange = { startDate = it },
                                endDate = endDate,
                                onEndDateChange = { endDate = it },
                                accounts = accounts,
                                showAdvancedFilters = showAdvancedFilters,
                                onShowAdvancedFiltersChange = { showAdvancedFilters = it },
                                onClearFilters = {
                                    filterStatus = null
                                    filterAccount = null
                                    filterSymbol = ""
                                    rankBy = "total_pnl"
                                    startDate = null
                                    endDate = null
                                }
                            )
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
                                        strategyHealthFlow = remember(performance.strategyId) { strategiesViewModel.strategyHealthFor(performance.strategyId) },
                                        onLoadStrategyHealth = { strategiesViewModel.loadStrategyHealth(it) },
                                        strategyRiskConfig = strategyRiskConfigs[performance.strategyId],
                                        isLoadingRisk = loadingStrategyRiskId == performance.strategyId,
                                        onLoadRiskConfig = { riskManagementViewModel.loadStrategyRiskConfig(performance.strategyId) },
                                        onCreateRiskConfig = { riskManagementViewModel.createStrategyRiskConfig(it) },
                                        onUpdateRiskConfig = { riskManagementViewModel.updateStrategyRiskConfig(performance.strategyId, it) },
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

// Card/detail composables -> StrategyCardAndDetails.kt (P1.2)
