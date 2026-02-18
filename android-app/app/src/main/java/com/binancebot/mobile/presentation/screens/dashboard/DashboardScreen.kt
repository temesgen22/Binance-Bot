package com.binancebot.mobile.presentation.screens.dashboard

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
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
import kotlinx.coroutines.delay

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

    // Offline support
    val isOnline = remember { androidx.compose.runtime.mutableStateOf(true) }
    val lastSyncTime = remember { androidx.compose.runtime.mutableStateOf<Long?>(null) }
    
    // Auto-refresh every 30 seconds
    LaunchedEffect(Unit) {
        while (true) {
            delay(30000)
            viewModel.refresh()
        }
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { 
                    Column {
                        Text("Dashboard", style = MaterialTheme.typography.titleLarge)
                        Text(
                            text = "Portfolio Overview",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                },
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
                            EmptyDashboardState(
                                onCreateStrategy = { navController.navigate("create_strategy") }
                            )
                        } else {
                            LazyColumn(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .weight(1f),
                                contentPadding = PaddingValues(Spacing.ScreenPadding),
                                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                            ) {
                                // Portfolio Summary Header (Hero Section)
                                item {
                                    PortfolioSummaryHeader(
                                        totalPnL = viewModel.totalPnL,
                                        realizedPnL = viewModel.realizedPnL,
                                        unrealizedPnL = viewModel.totalUnrealizedPnL,
                                        accountBalance = overview?.accountBalance,
                                        pnlChange24h = overview?.pnlChange24h,
                                        pnlChange7d = overview?.pnlChange7d
                                    )
                                }

                                // Risk Status Card
                                item {
                                    RiskStatusQuickCard(
                                        onClick = { navController.navigate(Screen.RiskManagement.route) }
                                    )
                                }

                                // Key Metrics Grid (2x3)
                                item {
                                    Text(
                                        text = "Performance Metrics",
                                        style = MaterialTheme.typography.titleMedium,
                                        fontWeight = FontWeight.Bold,
                                        modifier = Modifier.padding(vertical = Spacing.Small)
                                    )
                                }

                                item {
                                    MetricsGrid(
                                        winRate = overview?.overallWinRate ?: calculateWinRate(strategies).replace("%", "").toDoubleOrNull() ?: 0.0,
                                        totalTrades = overview?.totalTrades ?: viewModel.totalTrades,
                                        completedTrades = overview?.completedTrades ?: viewModel.completedTrades,
                                        activeStrategies = viewModel.activeStrategies,
                                        totalStrategies = viewModel.totalStrategies,
                                        profitFactor = null // StrategyPerformance doesn't have profitFactor field
                                    )
                                }

                                // Best/Worst Strategy Cards
                                overview?.let { ov ->
                                    if (ov.bestStrategy != null || ov.worstStrategy != null) {
                                        item {
                                            Row(
                                                modifier = Modifier.fillMaxWidth(),
                                                horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                                            ) {
                                                ov.bestStrategy?.let { best ->
                                                    BestWorstStrategyCard(
                                                        title = "Best Performer",
                                                        strategyName = best.strategyName,
                                                        pnl = best.totalPnl,
                                                        isBest = true,
                                                        modifier = Modifier.weight(1f),
                                                        onClick = { navController.navigate("strategy_details/${best.strategyId}") }
                                                    )
                                                }
                                                ov.worstStrategy?.let { worst ->
                                                    BestWorstStrategyCard(
                                                        title = "Needs Attention",
                                                        strategyName = worst.strategyName,
                                                        pnl = worst.totalPnl,
                                                        isBest = false,
                                                        modifier = Modifier.weight(1f),
                                                        onClick = { navController.navigate("strategy_details/${worst.strategyId}") }
                                                    )
                                                }
                                            }
                                        }
                                    }
                                }

                                // Top Symbol Card
                                overview?.topSymbol?.let { topSymbol ->
                                    item {
                                        TopSymbolCard(
                                            symbol = topSymbol.symbol,
                                            totalPnL = topSymbol.totalPnL,
                                            onClick = { navController.navigate(Screen.Trades.route) }
                                        )
                                    }
                                }

                                // Performance Charts Section
                                item {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text(
                                            text = "Performance Charts",
                                            style = MaterialTheme.typography.titleMedium,
                                            fontWeight = FontWeight.Bold
                                        )
                                    }
                                }

                                // PnL Timeline Chart
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
                                        EmptyChartCard(title = "PnL Timeline")
                                    }
                                }

                                // Quick Actions Section
                                item {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text(
                                            text = "Quick Actions",
                                            style = MaterialTheme.typography.titleMedium,
                                            fontWeight = FontWeight.Bold
                                        )
                                    }
                                }

                                item {
                                    QuickActionsGrid(
                                        onCreateStrategy = { navController.navigate("create_strategy") },
                                        onViewStrategies = { navController.navigate(Screen.Strategies.route) },
                                        onViewTrades = { navController.navigate(Screen.Trades.route) },
                                        onViewRisk = { navController.navigate(Screen.RiskManagement.route) }
                                    )
                                }

                                // Active Strategies Section
                                item {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text(
                                            text = "Active Strategies",
                                            style = MaterialTheme.typography.titleMedium,
                                            fontWeight = FontWeight.Bold
                                        )
                                        TextButton(onClick = { navController.navigate(Screen.Strategies.route) }) {
                                            Text("View All (${viewModel.totalStrategies})")
                                        }
                                    }
                                }

                                if (strategies.isEmpty()) {
                                    item {
                                        EmptyStrategiesCard(
                                            onCreateStrategy = { navController.navigate("create_strategy") }
                                        )
                                    }
                                } else {
                                    items(
                                        items = strategies.sortedByDescending { it.unrealizedPnL ?: 0.0 }.take(5),
                                        key = { it.id }
                                    ) { strategy ->
                                        EnhancedStrategyCard(
                                            strategy = strategy,
                                            onClick = { navController.navigate("strategy_details/${strategy.id}") }
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
// PortfolioSummaryHeader, PnLChangeChip, RiskStatusQuickCard, MetricsGrid, EnhancedMetricCard,
// BestWorstStrategyCard, TopSymbolCard, QuickActionsGrid, QuickActionCard, EnhancedStrategyCard,
// EmptyDashboardState, EmptyChartCard, EmptyStrategiesCard, calculateWinRate -> DashboardCards.kt (P1.3)

