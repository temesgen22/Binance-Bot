package com.binancebot.mobile.presentation.screens.trades

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
import kotlinx.coroutines.flow.collectLatest
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import androidx.paging.compose.collectAsLazyPagingItems
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.components.BottomNavigationBar
import com.binancebot.mobile.presentation.components.shouldShowBottomNav
import com.binancebot.mobile.presentation.components.OfflineIndicator
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.TradesViewModel
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TradesScreen(
    navController: NavController,
    viewModel: TradesViewModel = hiltViewModel()
) {
    val trades = viewModel.trades.collectAsLazyPagingItems()
    val currentRoute = navController.currentDestination?.route
    
    // Offline support - simplified for now
    val isOnline = remember { androidx.compose.runtime.mutableStateOf(true) }
    val lastSyncTime = remember { androidx.compose.runtime.mutableStateOf<Long?>(null) }
    
    // Filter state
    var showFilters by remember { mutableStateOf(false) }
    var filterStrategyId by remember { mutableStateOf<String?>(null) }
    var filterSymbol by remember { mutableStateOf<String?>(null) }
    var filterSide by remember { mutableStateOf<String?>(null) }
    var dateFrom by remember { mutableStateOf("") }
    var dateTo by remember { mutableStateOf("") }
    
    // Apply filters to ViewModel when they change
    LaunchedEffect(filterStrategyId, filterSymbol, dateFrom, dateTo) {
        viewModel.setFilters(
            strategyId = filterStrategyId,
            symbol = filterSymbol,
            dateFrom = if (dateFrom.isNotBlank()) dateFrom else null,
            dateTo = if (dateTo.isNotBlank()) dateTo else null
        )
    }
    
    // Collect visible trades for analytics
    val visibleTrades = remember { mutableStateListOf<com.binancebot.mobile.domain.model.Trade>() }
    
    // Calculate analytics from visible trades
    val tradeAnalytics = remember(visibleTrades.size, filterSide) {
        val filteredTrades = if (filterSide != null) {
            visibleTrades.filter { it.side.uppercase() == filterSide }
        } else {
            visibleTrades
        }
        
        val buyCount = filteredTrades.count { it.isBuy }
        val sellCount = filteredTrades.count { it.isSell }
        val totalNotional = filteredTrades.sumOf { it.notional }
        val totalCommission = filteredTrades.sumOf { it.commission ?: 0.0 }
        
        TradeAnalytics(
            totalTrades = filteredTrades.size,
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
                        Icon(
                            Icons.Default.FilterList,
                            contentDescription = "Filter",
                            tint = if (filterStrategyId != null || filterSymbol != null || filterSide != null || dateFrom.isNotBlank() || dateTo.isNotBlank()) {
                                MaterialTheme.colorScheme.primary
                            } else {
                                MaterialTheme.colorScheme.onSurface
                            }
                        )
                    }
                    IconButton(onClick = { trades.refresh() }) {
                        Icon(
                            Icons.Default.Refresh,
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
            // Offline Indicator
            OfflineIndicator(
                isOnline = isOnline.value,
                lastSyncTime = lastSyncTime.value,
                modifier = Modifier.fillMaxWidth()
            )
            
            when {
                trades.loadState.refresh is androidx.paging.LoadState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
                trades.loadState.refresh is androidx.paging.LoadState.Error -> {
                ErrorHandler(
                    message = (trades.loadState.refresh as androidx.paging.LoadState.Error).error.message
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
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
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
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .weight(1f)
                ) {
                    // Analytics Summary Card
                    if (visibleTrades.isNotEmpty()) {
                        TradeAnalyticsCard(
                            analytics = tradeAnalytics,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = Spacing.ScreenPadding, vertical = Spacing.Small)
                        )
                        
                        // Trade Distribution Chart
                        com.binancebot.mobile.presentation.components.charts.TradeDistributionChart(
                            buyCount = tradeAnalytics.buyTrades,
                            sellCount = tradeAnalytics.sellTrades,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = Spacing.ScreenPadding, vertical = Spacing.Small),
                            title = "Trade Distribution"
                        )
                    }
                    
                    // Filter Chips (when filters are shown)
                    if (showFilters) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = Spacing.ScreenPadding),
                            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                        ) {
                            // Side Filter
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                            ) {
                                FilterChip(
                                    selected = filterSide == null,
                                    onClick = { filterSide = null },
                                    label = { Text("All Sides") }
                                )
                                FilterChip(
                                    selected = filterSide == "BUY",
                                    onClick = { filterSide = if (filterSide == "BUY") null else "BUY" },
                                    label = { Text("Buy") }
                                )
                                FilterChip(
                                    selected = filterSide == "SELL",
                                    onClick = { filterSide = if (filterSide == "SELL") null else "SELL" },
                                    label = { Text("Sell") }
                                )
                            }
                            
                            // Date Range Filter
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
                                    onValueChange = { dateFrom = it },
                                    label = { Text("From Date") },
                                    placeholder = { Text("YYYY-MM-DD") },
                                    modifier = Modifier.weight(1f),
                                    trailingIcon = {
                                        Icon(Icons.Default.DateRange, contentDescription = "Pick Date")
                                    }
                                )
                                OutlinedTextField(
                                    value = dateTo,
                                    onValueChange = { dateTo = it },
                                    label = { Text("To Date") },
                                    placeholder = { Text("YYYY-MM-DD") },
                                    modifier = Modifier.weight(1f),
                                    trailingIcon = {
                                        Icon(Icons.Default.DateRange, contentDescription = "Pick Date")
                                    }
                                )
                            }
                            if (dateFrom.isNotBlank() || dateTo.isNotBlank()) {
                                TextButton(onClick = { 
                                    dateFrom = ""
                                    dateTo = ""
                                }) {
                                    Text("Clear Date Filter")
                                }
                            }
                        }
                        Spacer(modifier = Modifier.height(Spacing.Small))
                    }
                    
                    // Trades List
                    LazyColumn(
                        modifier = Modifier.weight(1f),
                        contentPadding = PaddingValues(Spacing.ScreenPadding),
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        items(
                            count = trades.itemCount,
                            key = { index -> trades[index]?.id ?: index.toString() }
                        ) { index ->
                            val trade = trades[index]
                            trade?.let {
                                // Track visible trades for analytics
                                if (!visibleTrades.contains(it)) {
                                    visibleTrades.add(it)
                                }
                                
                                // Apply client-side filtering if needed
                                val matchesFilter = when {
                                    filterSide != null && it.side.uppercase() != filterSide -> false
                                    else -> true
                                }
                                if (matchesFilter) {
                                    TradeCard(trade = it)
                                }
                            }
                        }
                        
                        // Loading indicator at bottom
                        if (trades.loadState.append is androidx.paging.LoadState.Loading) {
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
                    }
                }
                }
            }
        }
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
                    color = if (trade.isBuy) {
                        MaterialTheme.colorScheme.primaryContainer
                    } else {
                        MaterialTheme.colorScheme.errorContainer
                    }
                ) {
                    Text(
                        text = trade.side,
                        modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (trade.isBuy) {
                            MaterialTheme.colorScheme.onPrimaryContainer
                        } else {
                            MaterialTheme.colorScheme.onErrorContainer
                        }
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

private fun formatTimestamp(timestamp: Long): String {
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
