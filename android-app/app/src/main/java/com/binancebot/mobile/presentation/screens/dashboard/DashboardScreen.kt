package com.binancebot.mobile.presentation.screens.dashboard

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.presentation.components.BottomNavigationBar
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.components.OfflineIndicator
import com.binancebot.mobile.presentation.components.StatusBadge
import com.binancebot.mobile.presentation.components.SwipeRefreshBox
import com.binancebot.mobile.presentation.components.shouldShowBottomNav
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.DashboardUiState
import com.binancebot.mobile.presentation.viewmodel.DashboardViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    navController: NavController,
    viewModel: DashboardViewModel = hiltViewModel()
) {
    val strategies by viewModel.strategies.collectAsState()
    val dashboardOverview by viewModel.dashboardOverview.collectAsState()
    val uiState by viewModel.uiState.collectAsState()

    val isRefreshing = uiState is DashboardUiState.Loading
    val currentRoute = navController.currentDestination?.route

    // Offline support - simplified for now
    val isOnline = remember { androidx.compose.runtime.mutableStateOf(true) }
    val lastSyncTime = remember { androidx.compose.runtime.mutableStateOf<Long?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Dashboard") },
                actions = {
                    IconButton(onClick = { viewModel.refresh() }) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh",
                            tint = if (isRefreshing) {
                                MaterialTheme.colorScheme.primary
                            } else {
                                MaterialTheme.colorScheme.onSurface
                            }
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

            when (uiState) {
                is DashboardUiState.Loading -> {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .weight(1f),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator()
                    }
                }

                is DashboardUiState.Error -> {
                    ErrorHandler(
                        message = (uiState as DashboardUiState.Error).message,
                        onRetry = { viewModel.refresh() },
                        modifier = Modifier
                            .fillMaxSize()
                            .weight(1f)
                    )
                }

                else -> {
                    val overview = dashboardOverview
                    val hasData = overview != null || strategies.isNotEmpty()

                    SwipeRefreshBox(
                        isRefreshing = isRefreshing,
                        onRefresh = { viewModel.refresh() }
                    ) {
                        if (!hasData && uiState is DashboardUiState.Success) {
                            Box(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .weight(1f)
                                    .padding(Spacing.ScreenPadding),
                                contentAlignment = Alignment.Center
                            ) {
                                Column(
                                    horizontalAlignment = Alignment.CenterHorizontally,
                                    verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                                ) {
                                    Text(
                                        text = "No Dashboard Data",
                                        style = MaterialTheme.typography.headlineSmall,
                                        fontWeight = FontWeight.Bold
                                    )
                                    Text(
                                        text = "Start by creating a strategy to see your trading dashboard",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Spacer(modifier = Modifier.height(Spacing.Large))
                                    Button(onClick = { navController.navigate("create_strategy") }) {
                                        Text("Create Your First Strategy")
                                    }
                                }
                            }
                        } else {
                            LazyColumn(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .weight(1f),
                                contentPadding = PaddingValues(Spacing.ScreenPadding),
                                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                            ) {

                                item {
                                    MetricCard(
                                        title = "Total PnL",
                                        value = FormatUtils.formatCurrency(viewModel.totalPnL),
                                        modifier = Modifier.fillMaxWidth(),
                                        isHighlight = true
                                    )
                                }

                                item {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                                    ) {
                                        MetricCard(
                                            title = "Realized PnL",
                                            value = FormatUtils.formatCurrency(viewModel.realizedPnL),
                                            modifier = Modifier.weight(1f)
                                        )
                                        MetricCard(
                                            title = "Unrealized PnL",
                                            value = FormatUtils.formatCurrency(viewModel.totalUnrealizedPnL),
                                            modifier = Modifier.weight(1f)
                                        )
                                    }
                                }

                                // PnL changes
                                overview?.let { ov ->
                                    if (ov.pnlChange24h != null || ov.pnlChange7d != null || ov.pnlChange30d != null) {
                                        item {
                                            Row(
                                                modifier = Modifier.fillMaxWidth(),
                                                horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                                            ) {
                                                ov.pnlChange24h?.let { change24h ->
                                                    MetricCard(
                                                        title = "24h Change",
                                                        value = FormatUtils.formatCurrency(change24h),
                                                        modifier = Modifier.weight(1f)
                                                    )
                                                }
                                                ov.pnlChange7d?.let { change7d ->
                                                    MetricCard(
                                                        title = "7d Change",
                                                        value = FormatUtils.formatCurrency(change7d),
                                                        modifier = Modifier.weight(1f)
                                                    )
                                                }
                                                ov.pnlChange30d?.let { change30d ->
                                                    MetricCard(
                                                        title = "30d Change",
                                                        value = FormatUtils.formatCurrency(change30d),
                                                        modifier = Modifier.weight(1f)
                                                    )
                                                }
                                            }
                                        }
                                    }
                                }

                                // Metrics grid
                                item {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                                    ) {
                                        MetricCard(
                                            title = "Win Rate",
                                            value = overview?.let { String.format("%.1f%%", it.overallWinRate) }
                                                ?: calculateWinRate(strategies),
                                            modifier = Modifier.weight(1f)
                                        )
                                        MetricCard(
                                            title = "Total Trades",
                                            value = overview?.let { "${it.totalTrades}" } ?: "${viewModel.totalTrades}",
                                            modifier = Modifier.weight(1f)
                                        )
                                    }
                                }

                                item {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                                    ) {
                                        MetricCard(
                                            title = "Completed Trades",
                                            value = overview?.let { "${it.completedTrades}" } ?: "${viewModel.completedTrades}",
                                            modifier = Modifier.weight(1f)
                                        )
                                        MetricCard(
                                            title = "Active Strategies",
                                            value = "${viewModel.activeStrategies}/${viewModel.totalStrategies}",
                                            modifier = Modifier.weight(1f)
                                        )
                                    }
                                }

                                // Account balance
                                overview?.accountBalance?.let { balance ->
                                    item {
                                        MetricCard(
                                            title = "Account Balance",
                                            value = FormatUtils.formatCurrency(balance),
                                            modifier = Modifier.fillMaxWidth()
                                        )
                                    }
                                }

                                // Best/Worst + Top symbol
                                overview?.let { ov ->
                                    if (ov.bestStrategy != null || ov.worstStrategy != null) {
                                        item {
                                            Row(
                                                modifier = Modifier.fillMaxWidth(),
                                                horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                                            ) {
                                                ov.bestStrategy?.let { best ->
                                                    Card(
                                                        modifier = Modifier.weight(1f),
                                                        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                                                        colors = CardDefaults.cardColors(
                                                            containerColor = MaterialTheme.colorScheme.primaryContainer
                                                        )
                                                    ) {
                                                        Column(
                                                            modifier = Modifier
                                                                .fillMaxWidth()
                                                                .padding(Spacing.CardPadding),
                                                            horizontalAlignment = Alignment.CenterHorizontally
                                                        ) {
                                                            Text(
                                                                text = "Best Strategy",
                                                                style = MaterialTheme.typography.labelMedium,
                                                                color = MaterialTheme.colorScheme.onPrimaryContainer
                                                            )
                                                            Spacer(modifier = Modifier.height(Spacing.Tiny))
                                                            Text(
                                                                text = best.strategyName,
                                                                style = MaterialTheme.typography.bodySmall,
                                                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                                                                maxLines = 1
                                                            )
                                                            Spacer(modifier = Modifier.height(Spacing.Tiny))
                                                            Text(
                                                                text = FormatUtils.formatCurrency(best.totalPnl),
                                                                style = MaterialTheme.typography.titleMedium,
                                                                fontWeight = FontWeight.Bold,
                                                                color = MaterialTheme.colorScheme.onPrimaryContainer
                                                            )
                                                        }
                                                    }
                                                }

                                                ov.worstStrategy?.let { worst ->
                                                    Card(
                                                        modifier = Modifier.weight(1f),
                                                        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                                                        colors = CardDefaults.cardColors(
                                                            containerColor = MaterialTheme.colorScheme.errorContainer
                                                        )
                                                    ) {
                                                        Column(
                                                            modifier = Modifier
                                                                .fillMaxWidth()
                                                                .padding(Spacing.CardPadding),
                                                            horizontalAlignment = Alignment.CenterHorizontally
                                                        ) {
                                                            Text(
                                                                text = "Worst Strategy",
                                                                style = MaterialTheme.typography.labelMedium,
                                                                color = MaterialTheme.colorScheme.onErrorContainer
                                                            )
                                                            Spacer(modifier = Modifier.height(Spacing.Tiny))
                                                            Text(
                                                                text = worst.strategyName,
                                                                style = MaterialTheme.typography.bodySmall,
                                                                color = MaterialTheme.colorScheme.onErrorContainer,
                                                                maxLines = 1
                                                            )
                                                            Spacer(modifier = Modifier.height(Spacing.Tiny))
                                                            Text(
                                                                text = FormatUtils.formatCurrency(worst.totalPnl),
                                                                style = MaterialTheme.typography.titleMedium,
                                                                fontWeight = FontWeight.Bold,
                                                                color = MaterialTheme.colorScheme.onErrorContainer
                                                            )
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }

                                    ov.topSymbol?.let { topSymbol ->
                                        item {
                                            Card(
                                                modifier = Modifier.fillMaxWidth(),
                                                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                                            ) {
                                                Row(
                                                    modifier = Modifier
                                                        .fillMaxWidth()
                                                        .padding(Spacing.CardPadding),
                                                    horizontalArrangement = Arrangement.SpaceBetween,
                                                    verticalAlignment = Alignment.CenterVertically
                                                ) {
                                                    Column {
                                                        Text(
                                                            text = "Top Symbol",
                                                            style = MaterialTheme.typography.labelMedium,
                                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                                        )
                                                        Text(
                                                            text = topSymbol.symbol,
                                                            style = MaterialTheme.typography.titleMedium,
                                                            fontWeight = FontWeight.Bold
                                                        )
                                                    }
                                                    Column(horizontalAlignment = Alignment.End) {
                                                        Text(
                                                            text = FormatUtils.formatCurrency(topSymbol.totalPnL),
                                                            style = MaterialTheme.typography.titleMedium,
                                                            fontWeight = FontWeight.Bold,
                                                            color = if (topSymbol.totalPnL >= 0) {
                                                                MaterialTheme.colorScheme.primary
                                                            } else {
                                                                MaterialTheme.colorScheme.error
                                                            }
                                                        )
                                                        Text(
                                                            text = "Total PnL",
                                                            style = MaterialTheme.typography.bodySmall,
                                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                                        )
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }

                                // Performance chart section - FIXED (no extra elvis after remember)
                                item {
                                    val pnlData = remember(overview) {
                                        overview?.pnlTimeline?.let { timeline ->
                                            timeline.mapIndexedNotNull { index, entry ->
                                                try {
                                                    val timestamp = entry["timestamp"]
                                                    val pnl = entry["pnl"]
                                                    if (timestamp == null || pnl == null) return@mapIndexedNotNull null

                                                    val pnlValue = when (pnl) {
                                                        is Number -> pnl.toFloat()
                                                        is String -> pnl.toFloatOrNull() ?: return@mapIndexedNotNull null
                                                        else -> return@mapIndexedNotNull null
                                                    }

                                                    val dateLabel = when (timestamp) {
                                                        is String -> {
                                                            val formats = listOf(
                                                                "yyyy-MM-dd'T'HH:mm:ss",
                                                                "yyyy-MM-dd'T'HH:mm:ss.SSS",
                                                                "yyyy-MM-dd'T'HH:mm:ss'Z'",
                                                                "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
                                                                "yyyy-MM-dd HH:mm:ss",
                                                                "yyyy-MM-dd"
                                                            )
                                                            var parsed: java.util.Date? = null
                                                            for (format in formats) {
                                                                try {
                                                                    val df = java.text.SimpleDateFormat(
                                                                        format,
                                                                        java.util.Locale.getDefault()
                                                                    )
                                                                    df.timeZone = java.util.TimeZone.getTimeZone("UTC")
                                                                    parsed = df.parse(timestamp)
                                                                    break
                                                                } catch (_: Exception) {
                                                                }
                                                            }

                                                            if (parsed != null) {
                                                                val display = java.text.SimpleDateFormat(
                                                                    "MM/dd",
                                                                    java.util.Locale.getDefault()
                                                                )
                                                                display.format(parsed)
                                                            } else {
                                                                timestamp.take(10).ifEmpty { "#${index + 1}" }
                                                            }
                                                        }

                                                        is Number -> {
                                                            val t = timestamp.toLong()
                                                            val ms = if (t < 1_000_000_000_000L) t * 1000 else t
                                                            val date = java.util.Date(ms)
                                                            val display = java.text.SimpleDateFormat(
                                                                "MM/dd",
                                                                java.util.Locale.getDefault()
                                                            )
                                                            display.format(date)
                                                        }

                                                        else -> "#${index + 1}"
                                                    }

                                                    dateLabel to pnlValue
                                                } catch (_: Exception) {
                                                    null
                                                }
                                            }
                                        } ?: emptyList()
                                    }

                                    if (pnlData.isNotEmpty()) {
                                        com.binancebot.mobile.presentation.components.charts.PnLChart(
                                            data = pnlData,
                                            title = "PnL Timeline"
                                        )
                                    } else {
                                        Card(
                                            modifier = Modifier.fillMaxWidth(),
                                            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                                        ) {
                                            Column(
                                                modifier = Modifier
                                                    .fillMaxWidth()
                                                    .padding(Spacing.CardPadding),
                                                horizontalAlignment = Alignment.CenterHorizontally
                                            ) {
                                                Text(
                                                    text = "PnL Timeline",
                                                    style = MaterialTheme.typography.titleMedium,
                                                    fontWeight = FontWeight.Bold
                                                )
                                                Spacer(modifier = Modifier.height(Spacing.Medium))
                                                Text(
                                                    text = "No historical data available yet",
                                                    style = MaterialTheme.typography.bodyMedium,
                                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                                )
                                            }
                                        }
                                    }
                                }

                                // Win rate chart section (unchanged)
                                item {
                                    val winRateData = remember(strategies, overview) {
                                        strategies
                                            .filter { it.totalTrades != null && it.totalTrades > 0 }
                                            .mapNotNull { strategy ->
                                                val estimatedWinRate = when {
                                                    strategy.realizedPnL != null && strategy.realizedPnL > 0 -> {
                                                        60.0 + (strategy.realizedPnL / 100.0).coerceIn(-5.0, 10.0)
                                                    }

                                                    strategy.realizedPnL != null && strategy.realizedPnL < 0 -> {
                                                        40.0 + (strategy.realizedPnL / 100.0).coerceIn(-10.0, 5.0)
                                                    }

                                                    else -> 50.0
                                                }.coerceIn(0.0, 100.0)

                                                strategy.name to estimatedWinRate.toFloat()
                                            }
                                            .sortedByDescending { it.second }
                                            .take(5)
                                    }

                                    if (winRateData.isNotEmpty()) {
                                        com.binancebot.mobile.presentation.components.charts.WinRateChart(
                                            data = winRateData,
                                            title = "Win Rate by Strategy (Estimated)"
                                        )
                                    } else if (strategies.isEmpty() && overview == null) {
                                        Card(
                                            modifier = Modifier.fillMaxWidth(),
                                            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                                        ) {
                                            Column(
                                                modifier = Modifier
                                                    .fillMaxWidth()
                                                    .padding(Spacing.CardPadding),
                                                horizontalAlignment = Alignment.CenterHorizontally
                                            ) {
                                                Text(
                                                    text = "Win Rate by Strategy",
                                                    style = MaterialTheme.typography.titleMedium,
                                                    fontWeight = FontWeight.Bold
                                                )
                                                Spacer(modifier = Modifier.height(Spacing.Medium))
                                                Text(
                                                    text = "No strategy data available",
                                                    style = MaterialTheme.typography.bodyMedium,
                                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                                )
                                            }
                                        }
                                    }
                                }

                                // Strategy performance summary
                                if (strategies.isNotEmpty()) {
                                    item {
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Text(
                                                text = "Strategy Performance",
                                                style = MaterialTheme.typography.titleLarge,
                                                fontWeight = FontWeight.Bold
                                            )
                                            TextButton(onClick = { navController.navigate(Screen.Strategies.route) }) {
                                                Text("View All")
                                            }
                                        }
                                    }

                                    items(
                                        items = strategies.sortedByDescending { it.unrealizedPnL ?: 0.0 },
                                        key = { it.id }
                                    ) { strategy ->
                                        StrategySummaryCard(
                                            strategy = strategy,
                                            onClick = { navController.navigate("strategy_details/${strategy.id}") }
                                        )
                                    }
                                } else {
                                    item {
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
                                                    text = "No strategies yet",
                                                    style = MaterialTheme.typography.bodyLarge,
                                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                                )
                                                Spacer(modifier = Modifier.height(Spacing.Small))
                                                Button(onClick = { navController.navigate("create_strategy") }) {
                                                    Text("Create Your First Strategy")
                                                }
                                            }
                                        }
                                    }
                                }
                            } // ✅ close LazyColumn
                        }     // ✅ close else { LazyColumn(...) }
                    }         // ✅ close SwipeRefreshBox
                }             // ✅ close else -> in when(uiState)
            }                 // ✅ close when(uiState)
        }                     // ✅ close Column
    }                         // ✅ close Scaffold
}                             // ✅ close DashboardScreen

@Composable
fun MetricCard(
    title: String,
    value: String,
    modifier: Modifier = Modifier,
    isHighlight: Boolean = false
) {
    Card(
        modifier = modifier,
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = if (isHighlight) {
            CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
        } else {
            CardDefaults.cardColors()
        }
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.CardPadding),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.labelMedium,
                color = if (isHighlight) {
                    MaterialTheme.colorScheme.onPrimaryContainer
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                }
            )
            Spacer(modifier = Modifier.height(Spacing.Small))
            Text(
                text = value,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                color = if (isHighlight) {
                    MaterialTheme.colorScheme.onPrimaryContainer
                } else {
                    MaterialTheme.colorScheme.onSurface
                }
            )
        }
    }
}

@Composable
fun calculateWinRate(strategies: List<com.binancebot.mobile.domain.model.Strategy>): String {
    val strategiesWithTrades = strategies.filter { it.totalTrades != null && it.totalTrades > 0 }
    return if (strategiesWithTrades.isEmpty()) {
        "N/A"
    } else {
        val winningCount = strategiesWithTrades.count { (it.realizedPnL ?: 0.0) > 0 }
        val winRate = (winningCount.toDouble() / strategiesWithTrades.size) * 100
        String.format("%.1f%%", winRate)
    }
}

@Composable
fun StrategySummaryCard(
    strategy: com.binancebot.mobile.domain.model.Strategy,
    onClick: () -> Unit = {}
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.CardPadding),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = strategy.name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(Spacing.Tiny))
                Text(
                    text = "${strategy.symbol} • ${strategy.strategyType}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                if (strategy.hasPosition) {
                    Spacer(modifier = Modifier.height(Spacing.Tiny))
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "Position: ${strategy.positionSide ?: "N/A"}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary
                        )
                        strategy.positionSize?.let {
                            Text(
                                text = "• Size: ${FormatUtils.formatNumber(it)}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }

            Column(
                horizontalAlignment = Alignment.End,
                verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
            ) {
                StatusBadge(status = strategy.status)
                strategy.unrealizedPnL?.let {
                    Text(
                        text = FormatUtils.formatCurrency(it),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (it >= 0) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.error
                        }
                    )
                } ?: run {
                    Text(
                        text = "No PnL",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}
