@file:OptIn(ExperimentalMaterial3Api::class)

package com.binancebot.mobile.presentation.screens.trades

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.FilterList
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import androidx.paging.LoadState
import androidx.paging.compose.collectAsLazyPagingItems
import com.binancebot.mobile.presentation.components.BottomNavigationBar
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.components.OfflineIndicator
import com.binancebot.mobile.presentation.components.SwipeRefreshBox
import com.binancebot.mobile.presentation.components.shouldShowBottomNav
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.TradesViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun TradesScreen(
    navController: NavController,
    viewModel: TradesViewModel = hiltViewModel(),
    accountViewModel: com.binancebot.mobile.presentation.viewmodel.AccountViewModel = hiltViewModel()
) {
    val trades = viewModel.trades.collectAsLazyPagingItems()
    val currentRoute = navController.currentDestination?.route

    // PnL Overview data
    val pnlOverview by viewModel.pnlOverview.collectAsState()
    val allOpenPositions by viewModel.allOpenPositions.collectAsState()
    val overallStats by viewModel.overallStats.collectAsState()
    val pnlLoading by viewModel.pnlLoading.collectAsState()
    val availableSymbols by viewModel.availableSymbols.collectAsState()
    val accounts by accountViewModel.accounts.collectAsState()

    // Tab state
    var selectedTabIndex by remember { mutableStateOf(0) }

    // Offline support - simplified for now
    val isOnline = remember { mutableStateOf(true) }
    val lastSyncTime = remember { mutableStateOf<Long?>(null) }

    // Filter state
    var showFilters by remember { mutableStateOf(false) }
    var filterStrategyId by remember { mutableStateOf<String?>(null) }
    var filterSymbol by remember { mutableStateOf<String?>(null) }
    var filterSide by remember { mutableStateOf<String?>(null) }
    var filterAccountId by remember { mutableStateOf<String?>(null) }
    var dateFrom by remember { mutableStateOf("") }
    var dateTo by remember { mutableStateOf("") }

    // Load PnL overview when filters change
    LaunchedEffect(filterAccountId, dateFrom, dateTo) {
        viewModel.setFilters(
            accountId = filterAccountId,
            dateFrom = dateFrom.takeIf { it.isNotBlank() },
            dateTo = dateTo.takeIf { it.isNotBlank() }
        )
        if (selectedTabIndex == 0 || selectedTabIndex == 1) {
            viewModel.loadPnLOverview()
        }
    }

    // Apply filters to ViewModel when they change (for trades tab)
    LaunchedEffect(filterStrategyId, filterSymbol, filterSide, dateFrom, dateTo, filterAccountId) {
        viewModel.setFilters(
            strategyId = filterStrategyId,
            symbol = filterSymbol,
            side = filterSide,
            dateFrom = dateFrom.takeIf { it.isNotBlank() },
            dateTo = dateTo.takeIf { it.isNotBlank() },
            accountId = filterAccountId
        )
    }

    // Collect all loaded trades for analytics (not just visible ones)
    val allLoadedTrades = remember { mutableStateListOf<com.binancebot.mobile.domain.model.Trade>() }

    // Calculate analytics from all loaded trades
    val tradeAnalytics = remember(allLoadedTrades.size) {
        val buyCount = allLoadedTrades.count { it.isBuy }
        val sellCount = allLoadedTrades.count { it.isSell }
        val totalNotional = allLoadedTrades.sumOf { it.notional }
        val totalCommission = allLoadedTrades.sumOf { it.commission ?: 0.0 }

        TradeAnalytics(
            totalTrades = allLoadedTrades.size,
            buyTrades = buyCount,
            sellTrades = sellCount,
            totalNotional = totalNotional,
            totalCommission = totalCommission
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Trades") },
                actions = {
                    IconButton(onClick = { showFilters = !showFilters }) {
                        val hasAnyFilter =
                            filterStrategyId != null ||
                                    filterSymbol != null ||
                                    filterSide != null ||
                                    filterAccountId != null ||
                                    dateFrom.isNotBlank() ||
                                    dateTo.isNotBlank()

                        Icon(
                            imageVector = Icons.Default.FilterList,
                            contentDescription = "Filter",
                            tint = if (hasAnyFilter) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.onSurface
                        )
                    }

                    IconButton(
                        onClick = {
                            when (selectedTabIndex) {
                                0, 1 -> viewModel.loadPnLOverview()
                                2 -> trades.refresh()
                            }
                        }
                    ) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh"
                        )
                    }
                }
            )
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
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            OfflineIndicator(
                isOnline = isOnline.value,
                lastSyncTime = lastSyncTime.value,
                modifier = Modifier.fillMaxWidth()
            )

            if (selectedTabIndex != 2 || trades.itemCount > 0) {
                OverallStatsCard(
                    stats = overallStats,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = Spacing.ScreenPadding, vertical = Spacing.Small)
                )
            }

            TabRow(selectedTabIndex = selectedTabIndex) {
                Tab(
                    selected = selectedTabIndex == 0,
                    onClick = { selectedTabIndex = 0 },
                    text = { Text("Overview") }
                )
                Tab(
                    selected = selectedTabIndex == 1,
                    onClick = { selectedTabIndex = 1 },
                    text = { Text("Positions") }
                )
                Tab(
                    selected = selectedTabIndex == 2,
                    onClick = { selectedTabIndex = 2 },
                    text = { Text("All Trades") }
                )
            }

            when (selectedTabIndex) {
                0 -> {
                    OverviewTab(
                        pnlOverview = pnlOverview,
                        isLoading = pnlLoading,
                        onRefresh = { viewModel.loadPnLOverview() },
                        modifier = Modifier.weight(1f)
                    )
                }

                1 -> {
                    PositionsTab(
                        positions = allOpenPositions,
                        isLoading = pnlLoading,
                        onRefresh = { viewModel.loadPnLOverview() },
                        modifier = Modifier.weight(1f)
                    )
                }

                2 -> {
                    // ✅ Clean, balanced braces for Paging states
                    when {
                        trades.loadState.refresh is LoadState.Loading -> {
                            Box(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .weight(1f),
                                contentAlignment = Alignment.Center
                            ) {
                                CircularProgressIndicator()
                            }
                        }

                        trades.loadState.refresh is LoadState.Error -> {
                            ErrorHandler(
                                message = (trades.loadState.refresh as LoadState.Error).error.message
                                    ?: "Failed to load trades",
                                onRetry = { trades.retry() },
                                modifier = Modifier
                                    .fillMaxSize()
                                    .weight(1f)
                            )
                        }

                        trades.itemCount == 0 -> {
                            Box(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .weight(1f),
                                contentAlignment = Alignment.Center
                            ) {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Text(
                                        text = "No trades found",
                                        style = MaterialTheme.typography.titleMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Spacer(modifier = Modifier.height(Spacing.Small))
                                    Text(
                                        text = "Trades will appear here once your strategies start trading",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }

                        else -> {
                            SwipeRefreshBox(
                                isRefreshing = trades.loadState.refresh is LoadState.Loading,
                                onRefresh = { trades.refresh() }
                            ) {
                                Column(
                                    modifier = Modifier
                                        .fillMaxSize()
                                        .weight(1f)
                                ) {
                                    if (allLoadedTrades.isNotEmpty()) {
                                        TradeAnalyticsCard(
                                            analytics = tradeAnalytics,
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .padding(
                                                    horizontal = Spacing.ScreenPadding,
                                                    vertical = Spacing.Small
                                                )
                                        )

                                        com.binancebot.mobile.presentation.components.charts.TradeDistributionChart(
                                            buyCount = tradeAnalytics.buyTrades,
                                            sellCount = tradeAnalytics.sellTrades,
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .padding(
                                                    horizontal = Spacing.ScreenPadding,
                                                    vertical = Spacing.Small
                                                ),
                                            title = "Trade Distribution"
                                        )
                                    }

                                    if (showFilters) {
                                        FiltersSection(
                                            accounts = accounts,
                                            availableSymbols = availableSymbols,
                                            filterAccountId = filterAccountId,
                                            onFilterAccountId = { filterAccountId = it },
                                            filterSide = filterSide,
                                            onFilterSide = { filterSide = it },
                                            filterStrategyId = filterStrategyId,
                                            onFilterStrategyId = { filterStrategyId = it },
                                            filterSymbol = filterSymbol,
                                            onFilterSymbol = { filterSymbol = it },
                                            dateFrom = dateFrom,
                                            onDateFrom = { dateFrom = it },
                                            dateTo = dateTo,
                                            onDateTo = { dateTo = it },
                                            onClearAll = {
                                                filterStrategyId = null
                                                filterSymbol = null
                                                filterSide = null
                                                filterAccountId = null
                                                dateFrom = ""
                                                dateTo = ""
                                            },
                                            modifier = Modifier.fillMaxWidth()
                                        )
                                    }

                                    LazyColumn(
                                        modifier = Modifier.weight(1f),
                                        contentPadding = PaddingValues(Spacing.ScreenPadding),
                                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                                    ) {
                                        // ✅ Use count-based items overload from LazyListScope
                                        items(
                                            count = trades.itemCount,
                                            key = { index -> trades[index]?.id ?: index.toString() }
                                        ) { index ->
                                            val trade = trades[index]
                                            trade?.let {
                                                if (!allLoadedTrades.any { existing -> existing.id == it.id }) {
                                                    allLoadedTrades.add(it)
                                                }
                                                TradeCard(trade = it)
                                            }
                                        }

                                        if (trades.loadState.append is LoadState.Loading) {
                                            item {
                                                Box(
                                                    modifier = Modifier
                                                        .fillMaxWidth()
                                                        .padding(Spacing.Medium),
                                                    contentAlignment = Alignment.Center
                                                ) {
                                                    CircularProgressIndicator()
                                                }
                                            }
                                        }

                                        if (trades.loadState.append is LoadState.Error) {
                                            item {
                                                Card(
                                                    modifier = Modifier
                                                        .fillMaxWidth()
                                                        .padding(Spacing.Medium),
                                                    colors = CardDefaults.cardColors(
                                                        containerColor = MaterialTheme.colorScheme.errorContainer
                                                    )
                                                ) {
                                                    Column(
                                                        modifier = Modifier
                                                            .fillMaxWidth()
                                                            .padding(Spacing.Medium),
                                                        horizontalAlignment = Alignment.CenterHorizontally
                                                    ) {
                                                        Text(
                                                            text = "Failed to load more trades",
                                                            style = MaterialTheme.typography.bodyMedium,
                                                            color = MaterialTheme.colorScheme.onErrorContainer
                                                        )
                                                        Spacer(modifier = Modifier.height(Spacing.Small))
                                                        TextButton(onClick = { trades.retry() }) {
                                                            Text(
                                                                "Retry",
                                                                color = MaterialTheme.colorScheme.onErrorContainer
                                                            )
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
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FiltersSection(
    accounts: List<com.binancebot.mobile.domain.model.Account>,
    availableSymbols: List<String>,
    filterAccountId: String?,
    onFilterAccountId: (String?) -> Unit,
    filterSide: String?,
    onFilterSide: (String?) -> Unit,
    filterStrategyId: String?,
    onFilterStrategyId: (String?) -> Unit,
    filterSymbol: String?,
    onFilterSymbol: (String?) -> Unit,
    dateFrom: String,
    onDateFrom: (String) -> Unit,
    dateTo: String,
    onDateTo: (String) -> Unit,
    onClearAll: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.padding(horizontal = Spacing.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
    ) {
        Text(
            text = "Trade Side",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            FilterChip(
                selected = filterSide == null,
                onClick = { onFilterSide(null) },
                label = { Text("All Sides") }
            )
            FilterChip(
                selected = filterSide == "BUY",
                onClick = { onFilterSide(if (filterSide == "BUY") null else "BUY") },
                label = { Text("Buy") }
            )
            FilterChip(
                selected = filterSide == "SELL",
                onClick = { onFilterSide(if (filterSide == "SELL") null else "SELL") },
                label = { Text("Sell") }
            )
        }

        Text(
            text = "Account",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        var accountExpanded by remember { mutableStateOf(false) }
        ExposedDropdownMenuBox(
            expanded = accountExpanded,
            onExpandedChange = { accountExpanded = !accountExpanded }
        ) {
            OutlinedTextField(
                value = accounts.find { it.accountId == filterAccountId }?.name ?: filterAccountId.orEmpty(),
                onValueChange = {},
                readOnly = true,
                label = { Text("Account") },
                placeholder = { Text("All Accounts") },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(),
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = accountExpanded) }
            )
            ExposedDropdownMenu(
                expanded = accountExpanded,
                onDismissRequest = { accountExpanded = false }
            ) {
                DropdownMenuItem(
                    text = { Text("All Accounts") },
                    onClick = {
                        onFilterAccountId(null)
                        accountExpanded = false
                    }
                )
                accounts.forEach { account ->
                    DropdownMenuItem(
                        text = { Text("${account.name ?: account.accountId}${if (account.testnet) " [TESTNET]" else ""}") },
                        onClick = {
                            onFilterAccountId(account.accountId)
                            accountExpanded = false
                        }
                    )
                }
            }
        }

        Text(
            text = "Strategy",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = Spacing.Small)
        )
        OutlinedTextField(
            value = filterStrategyId ?: "",
            onValueChange = { onFilterStrategyId(it.ifBlank { null }) },
            label = { Text("Strategy ID") },
            placeholder = { Text("Enter strategy ID") },
            modifier = Modifier.fillMaxWidth()
        )

        Text(
            text = "Symbol",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = Spacing.Small)
        )

        if (availableSymbols.isNotEmpty()) {
            var symbolExpanded by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(
                expanded = symbolExpanded,
                onExpandedChange = { symbolExpanded = !symbolExpanded }
            ) {
                OutlinedTextField(
                    value = filterSymbol ?: "",
                    onValueChange = { 
                        val newValue = it.ifBlank { null }
                        onFilterSymbol(newValue?.uppercase())
                    },
                    label = { Text("Symbol") },
                    placeholder = { Text("e.g., BTCUSDT") },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor(),
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = symbolExpanded) }
                )
                ExposedDropdownMenu(
                    expanded = symbolExpanded,
                    onDismissRequest = { symbolExpanded = false }
                ) {
                    DropdownMenuItem(
                        text = { Text("All Symbols") },
                        onClick = {
                            onFilterSymbol(null)
                            symbolExpanded = false
                        }
                    )
                    availableSymbols.forEach { symbol ->
                        DropdownMenuItem(
                            text = { Text(symbol) },
                            onClick = {
                                onFilterSymbol(symbol)
                                symbolExpanded = false
                            }
                        )
                    }
                }
            }
        } else {
            OutlinedTextField(
                value = filterSymbol ?: "",
                onValueChange = { 
                    val newValue = it.ifBlank { null }
                    onFilterSymbol(newValue?.uppercase())
                },
                label = { Text("Symbol") },
                placeholder = { Text("e.g., BTCUSDT") },
                modifier = Modifier.fillMaxWidth()
            )
        }

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
                value = dateFrom,
                onValueChange = onDateFrom,
                label = { Text("From Date") },
                placeholder = { Text("YYYY-MM-DD") },
                modifier = Modifier.weight(1f),
                trailingIcon = { Icon(Icons.Default.DateRange, contentDescription = "Pick Date") }
            )
            OutlinedTextField(
                value = dateTo,
                onValueChange = onDateTo,
                label = { Text("To Date") },
                placeholder = { Text("YYYY-MM-DD") },
                modifier = Modifier.weight(1f),
                trailingIcon = { Icon(Icons.Default.DateRange, contentDescription = "Pick Date") }
            )
        }

        val hasAnyFilter =
            filterStrategyId != null ||
                    filterSymbol != null ||
                    filterSide != null ||
                    filterAccountId != null ||
                    dateFrom.isNotBlank() ||
                    dateTo.isNotBlank()

        if (hasAnyFilter) {
            TextButton(onClick = onClearAll) {
                Text("Clear All Filters")
            }
        }

        Spacer(modifier = Modifier.height(Spacing.Small))
    }
}

@Composable
fun TradeCard(trade: com.binancebot.mobile.domain.model.Trade) {
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
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = trade.symbol,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = if (trade.isEntry) "Entry" else "Exit: ${trade.exitReason ?: "N/A"}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                Surface(
                    shape = MaterialTheme.shapes.small,
                    color = if (trade.isBuy) MaterialTheme.colorScheme.primaryContainer
                    else MaterialTheme.colorScheme.errorContainer
                ) {
                    Text(
                        text = trade.side,
                        modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (trade.isBuy) MaterialTheme.colorScheme.onPrimaryContainer
                        else MaterialTheme.colorScheme.onErrorContainer
                    )
                }
            }

            Divider()

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text(
                        text = "Quantity",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = String.format("%.4f", trade.executedQty),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
                Column {
                    Text(
                        text = "Price",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = FormatUtils.formatCurrency(trade.avgPrice),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
                Column {
                    Text(
                        text = "Notional",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = FormatUtils.formatCurrency(trade.notional),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            trade.commission?.let { commission ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = "Commission",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = FormatUtils.formatCurrency(commission),
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }

            Text(
                text = formatTimestamp(trade.timestamp),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

fun formatTimestamp(timestamp: Long): String {
    val sdf = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
    return sdf.format(Date(timestamp))
}

data class TradeAnalytics(
    val totalTrades: Int,
    val buyTrades: Int,
    val sellTrades: Int,
    val totalNotional: Double,
    val totalCommission: Double
)

@Composable
fun TradeAnalyticsCard(
    analytics: TradeAnalytics,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier,
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = "Total Trades",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
                Text(
                    text = analytics.totalTrades.toString(),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = "Buy",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
                Text(
                    text = analytics.buyTrades.toString(),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = "Sell",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
                Text(
                    text = analytics.sellTrades.toString(),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
            }
        }
    }
}
