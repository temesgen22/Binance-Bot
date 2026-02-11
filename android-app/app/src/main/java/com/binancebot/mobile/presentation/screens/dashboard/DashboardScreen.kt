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

// Portfolio Summary Header (Hero Section)
@Composable
private fun PortfolioSummaryHeader(
    totalPnL: Double,
    realizedPnL: Double,
    unrealizedPnL: Double,
    accountBalance: Double?,
    pnlChange24h: Double?,
    pnlChange7d: Double?
) {
    val isPositive = totalPnL >= 0
    val gradientColors = if (isPositive) {
        listOf(
            Color(0xFF667eea),
            Color(0xFF764ba2)
        )
    } else {
        listOf(
            Color(0xFFf093fb),
            Color(0xFFf5576c)
        )
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
        shape = RoundedCornerShape(16.dp)
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    brush = Brush.linearGradient(gradientColors)
                )
                .padding(Spacing.Large)
        ) {
            Column(
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(
                            text = "Total Portfolio PnL",
                            style = MaterialTheme.typography.bodyMedium,
                            color = Color.White.copy(alpha = 0.9f)
                        )
                        Spacer(modifier = Modifier.height(Spacing.Tiny))
                        Text(
                            text = FormatUtils.formatCurrency(totalPnL),
                            style = MaterialTheme.typography.displaySmall,
                            fontWeight = FontWeight.Bold,
                            color = Color.White
                        )
                    }
                    Icon(
                        imageVector = if (isPositive) Icons.Default.TrendingUp else Icons.Default.TrendingDown,
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(32.dp)
                    )
                }

                HorizontalDivider(color = Color.White.copy(alpha = 0.3f))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column {
                        Text(
                            text = "Realized",
                            style = MaterialTheme.typography.bodySmall,
                            color = Color.White.copy(alpha = 0.8f)
                        )
                        Text(
                            text = FormatUtils.formatCurrency(realizedPnL),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = Color.White
                        )
                    }
                    Column {
                        Text(
                            text = "Unrealized",
                            style = MaterialTheme.typography.bodySmall,
                            color = Color.White.copy(alpha = 0.8f)
                        )
                        Text(
                            text = FormatUtils.formatCurrency(unrealizedPnL),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = Color.White
                        )
                    }
                }

                accountBalance?.let { balance ->
                    HorizontalDivider(color = Color.White.copy(alpha = 0.3f))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "Account Balance",
                            style = MaterialTheme.typography.bodyMedium,
                            color = Color.White.copy(alpha = 0.9f)
                        )
                        Text(
                            text = FormatUtils.formatCurrency(balance),
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = Color.White
                        )
                    }
                }

                // PnL Changes
                if (pnlChange24h != null || pnlChange7d != null) {
                    HorizontalDivider(color = Color.White.copy(alpha = 0.3f))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceEvenly
                    ) {
                        pnlChange24h?.let { change ->
                            PnLChangeChip(
                                label = "24h",
                                value = change,
                                modifier = Modifier.weight(1f)
                            )
                        }
                        pnlChange7d?.let { change ->
                            PnLChangeChip(
                                label = "7d",
                                value = change,
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PnLChangeChip(
    label: String,
    value: Double,
    modifier: Modifier = Modifier
) {
    val isPositive = value >= 0
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = Color.White.copy(alpha = 0.8f)
        )
        Text(
            text = "${if (isPositive) "+" else ""}${FormatUtils.formatCurrency(value)}",
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Bold,
            color = Color.White
        )
    }
}

// Risk Status Quick Card
@Composable
private fun RiskStatusQuickCard(
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(Spacing.Medium),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Default.Shield,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(32.dp)
                )
                Column {
                    Text(
                        text = "Risk Management",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                    Text(
                        text = "View portfolio risk status and metrics",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f)
                    )
                }
            }
            Icon(
                imageVector = Icons.Default.ChevronRight,
                contentDescription = "View Risk Management",
                tint = MaterialTheme.colorScheme.onPrimaryContainer
            )
        }
    }
}

// Metrics Grid (2x3)
@Composable
private fun MetricsGrid(
    winRate: Double,
    totalTrades: Int,
    completedTrades: Int,
    activeStrategies: Int,
    totalStrategies: Int,
    profitFactor: Double?
) {
    Column(
        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
    ) {
        // Row 1
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            EnhancedMetricCard(
                title = "Win Rate",
                value = String.format("%.1f%%", winRate),
                icon = Icons.Default.CheckCircle,
                modifier = Modifier.weight(1f)
            )
            EnhancedMetricCard(
                title = "Total Trades",
                value = totalTrades.toString(),
                icon = Icons.Default.SwapHoriz,
                modifier = Modifier.weight(1f)
            )
        }
        // Row 2
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            EnhancedMetricCard(
                title = "Completed",
                value = completedTrades.toString(),
                icon = Icons.Default.Done,
                modifier = Modifier.weight(1f)
            )
            EnhancedMetricCard(
                title = "Active",
                value = "$activeStrategies/$totalStrategies",
                icon = Icons.Default.PlayArrow,
                modifier = Modifier.weight(1f)
            )
        }
        // Row 3
        profitFactor?.let {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                EnhancedMetricCard(
                    title = "Profit Factor",
                    value = String.format("%.2f", it),
                    icon = Icons.Default.Star,
                    modifier = Modifier.weight(1f)
                )
            }
        }
    }
}

@Composable
private fun EnhancedMetricCard(
    title: String,
    value: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier,
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(24.dp)
            )
            Spacer(modifier = Modifier.height(Spacing.Small))
            Text(
                text = value,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold
            )
            Text(
                text = title,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

// Best/Worst Strategy Card
@Composable
private fun BestWorstStrategyCard(
    title: String,
    strategyName: String,
    pnl: Double,
    isBest: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Card(
        modifier = modifier.clickable(onClick = onClick),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (isBest) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.errorContainer
            }
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(
                imageVector = if (isBest) Icons.Default.Star else Icons.Default.Warning,
                contentDescription = null,
                tint = if (isBest) {
                    MaterialTheme.colorScheme.primary
                } else {
                    MaterialTheme.colorScheme.error
                },
                modifier = Modifier.size(28.dp)
            )
            Spacer(modifier = Modifier.height(Spacing.Small))
            Text(
                text = title,
                style = MaterialTheme.typography.labelMedium,
                color = if (isBest) {
                    MaterialTheme.colorScheme.onPrimaryContainer
                } else {
                    MaterialTheme.colorScheme.onErrorContainer
                }
            )
            Text(
                text = strategyName,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                color = if (isBest) {
                    MaterialTheme.colorScheme.onPrimaryContainer
                } else {
                    MaterialTheme.colorScheme.onErrorContainer
                }
            )
            Text(
                text = FormatUtils.formatCurrency(pnl),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = if (isBest) {
                    MaterialTheme.colorScheme.onPrimaryContainer
                } else {
                    MaterialTheme.colorScheme.onErrorContainer
                }
            )
        }
    }
}

// Top Symbol Card
@Composable
private fun TopSymbolCard(
    symbol: String,
    totalPnL: Double,
    onClick: () -> Unit
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
                .padding(Spacing.Medium),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(Spacing.Medium),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Default.TrendingUp,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(32.dp)
                )
                Column {
                    Text(
                        text = "Top Performing Symbol",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = symbol,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = FormatUtils.formatCurrency(totalPnL),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = if (totalPnL >= 0) {
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

// Quick Actions Grid
@Composable
private fun QuickActionsGrid(
    onCreateStrategy: () -> Unit,
    onViewStrategies: () -> Unit,
    onViewTrades: () -> Unit,
    onViewRisk: () -> Unit
) {
    Column(
        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            QuickActionCard(
                title = "New Strategy",
                icon = Icons.Default.Add,
                onClick = onCreateStrategy,
                modifier = Modifier.weight(1f)
            )
            QuickActionCard(
                title = "Strategies",
                icon = Icons.Default.List,
                onClick = onViewStrategies,
                modifier = Modifier.weight(1f)
            )
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            QuickActionCard(
                title = "Trades",
                icon = Icons.Default.SwapHoriz,
                onClick = onViewTrades,
                modifier = Modifier.weight(1f)
            )
            QuickActionCard(
                title = "Risk",
                icon = Icons.Default.Shield,
                onClick = onViewRisk,
                modifier = Modifier.weight(1f)
            )
        }
    }
}

@Composable
private fun QuickActionCard(
    title: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.clickable(onClick = onClick),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(
                imageVector = icon,
                contentDescription = title,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(32.dp)
            )
            Spacer(modifier = Modifier.height(Spacing.Small))
            Text(
                text = title,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
                textAlign = TextAlign.Center
            )
        }
    }
}

// Enhanced Strategy Card
@Composable
private fun EnhancedStrategyCard(
    strategy: com.binancebot.mobile.domain.model.Strategy,
    onClick: () -> Unit
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
                .padding(Spacing.Medium),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = strategy.name,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    StatusBadge(status = strategy.status)
                }
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
                        Icon(
                            imageVector = Icons.Default.ShowChart,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp),
                            tint = MaterialTheme.colorScheme.primary
                        )
                        Text(
                            text = "${strategy.positionSide ?: "N/A"} • ${FormatUtils.formatNumber(strategy.positionSize ?: 0.0)}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary
                        )
                    }
                }
            }

            Column(
                horizontalAlignment = Alignment.End,
                verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
            ) {
                strategy.unrealizedPnL?.let {
                    Text(
                        text = FormatUtils.formatCurrency(it),
                        style = MaterialTheme.typography.titleMedium,
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
                Icon(
                    imageVector = Icons.Default.ChevronRight,
                    contentDescription = "View Details",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

// Empty States
@Composable
private fun EmptyDashboardState(
    onCreateStrategy: () -> Unit
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .padding(Spacing.ScreenPadding),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            Icon(
                imageVector = Icons.Default.Dashboard,
                contentDescription = null,
                modifier = Modifier.size(64.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                text = "No Dashboard Data",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold
            )
            Text(
                text = "Start by creating a strategy to see your trading dashboard",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center
            )
            Spacer(modifier = Modifier.height(Spacing.Large))
            Button(onClick = onCreateStrategy) {
                Text("Create Your First Strategy")
            }
        }
    }
}

@Composable
private fun EmptyChartCard(title: String) {
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
                text = title,
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

@Composable
private fun EmptyStrategiesCard(
    onCreateStrategy: () -> Unit
) {
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
            Icon(
                imageVector = Icons.Default.PlayArrow,
                contentDescription = null,
                modifier = Modifier.size(48.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(modifier = Modifier.height(Spacing.Medium))
            Text(
                text = "No strategies yet",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(modifier = Modifier.height(Spacing.Small))
            Button(onClick = onCreateStrategy) {
                Text("Create Your First Strategy")
            }
        }
    }
}

@Composable
fun calculateWinRate(strategies: List<com.binancebot.mobile.domain.model.Strategy>): String {
    val strategiesWithTrades = strategies.filter { it.totalTrades != null && it.totalTrades > 0 }
    return if (strategiesWithTrades.isEmpty()) {
        "0.0%"
    } else {
        val winningCount = strategiesWithTrades.count { (it.realizedPnL ?: 0.0) > 0 }
        val winRate = (winningCount.toDouble() / strategiesWithTrades.size) * 100
        String.format("%.1f%%", winRate)
    }
}
