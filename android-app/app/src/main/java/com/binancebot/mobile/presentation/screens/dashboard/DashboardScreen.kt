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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlin.math.absoluteValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.components.StatusBadge
import com.binancebot.mobile.presentation.components.BottomNavigationBar
import com.binancebot.mobile.presentation.components.shouldShowBottomNav
import com.binancebot.mobile.presentation.components.OfflineIndicator
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.DashboardViewModel
import com.binancebot.mobile.presentation.viewmodel.DashboardUiState
import androidx.compose.runtime.remember

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    navController: NavController,
    viewModel: DashboardViewModel = hiltViewModel()
) {
    val strategies by viewModel.strategies.collectAsState()
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
                            Icons.Default.Refresh,
                            contentDescription = "Refresh",
                            tint = if (isRefreshing) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface
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
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .weight(1f),
                    contentPadding = PaddingValues(Spacing.ScreenPadding),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    // Main PnL Card (Highlighted)
                    item {
                        MetricCard(
                            title = "Total Unrealized PnL",
                            value = FormatUtils.formatCurrency(viewModel.totalUnrealizedPnL),
                            modifier = Modifier.fillMaxWidth(),
                            isHighlight = true
                        )
                    }
                    
                    // Metrics Grid (2x3) - Phase 1.3 Requirement
                    item {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                        ) {
                            MetricCard(
                                title = "Total PnL",
                                value = FormatUtils.formatCurrency(viewModel.totalUnrealizedPnL),
                                modifier = Modifier.weight(1f)
                            )
                            MetricCard(
                                title = "Win Rate",
                                value = calculateWinRate(strategies),
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
                                title = "Profit Factor",
                                value = calculateProfitFactor(strategies),
                                modifier = Modifier.weight(1f)
                            )
                            MetricCard(
                                title = "Sharpe Ratio",
                                value = "N/A", // TODO: Calculate from strategy performance data
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
                                title = "Max Drawdown",
                                value = "N/A", // TODO: Get from risk management or strategy stats
                                modifier = Modifier.weight(1f)
                            )
                            MetricCard(
                                title = "Total Trades",
                                value = "N/A", // TODO: Get from strategy stats API
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }
                    
                    // Performance Chart Section
                    item {
                        val pnlData = remember(strategies) {
                            // Generate sample PnL data from strategies
                            // In real implementation, this would come from historical data
                            strategies.mapIndexed { index, strategy ->
                                val date = java.text.SimpleDateFormat("MM/dd", java.util.Locale.getDefault())
                                    .format(java.util.Date(System.currentTimeMillis() - (30 - index) * 86400000L))
                                date to (strategy.unrealizedPnL?.toFloat() ?: 0f)
                            }.takeLast(7) // Last 7 days
                        }
                        
                        com.binancebot.mobile.presentation.components.charts.PnLChart(
                            data = pnlData,
                            title = "PnL Overview (Last 7 Days)"
                        )
                    }
                    
                    // Win Rate Chart
                    item {
                        val winRateData = remember(strategies) {
                            strategies.map { strategy ->
                                strategy.name to ((strategy.realizedPnL ?: 0.0) / (strategy.totalTrades ?: 1).coerceAtLeast(1) * 100).toFloat()
                            }.take(5) // Top 5 strategies
                        }
                        
                        if (winRateData.isNotEmpty()) {
                            com.binancebot.mobile.presentation.components.charts.WinRateChart(
                                data = winRateData,
                                title = "Win Rate by Strategy"
                            )
                        }
                    }
                    
                    // Strategy Performance Summary
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
                                TextButton(
                                    onClick = { navController.navigate(Screen.Strategies.route) }
                                ) {
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
                                onClick = {
                                    navController.navigate("strategy_details/${strategy.id}")
                                }
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
                                    Button(
                                        onClick = { navController.navigate("create_strategy") }
                                    ) {
                                        Text("Create Your First Strategy")
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
            CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.primaryContainer
            )
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

// Helper functions for metrics calculation
@Composable
private fun calculateWinRate(strategies: List<com.binancebot.mobile.domain.model.Strategy>): String {
    val strategiesWithPnL = strategies.filter { it.unrealizedPnL != null }
    return if (strategiesWithPnL.isEmpty()) {
        "N/A"
    } else {
        val winningCount = strategiesWithPnL.count { (it.unrealizedPnL ?: 0.0) > 0 }
        val winRate = (winningCount.toDouble() / strategiesWithPnL.size) * 100
        String.format("%.1f%%", winRate)
    }
}

@Composable
private fun calculateProfitFactor(strategies: List<com.binancebot.mobile.domain.model.Strategy>): String {
    val totalProfit = strategies.sumOf { (it.unrealizedPnL ?: 0.0).coerceAtLeast(0.0) }
    val totalLoss = strategies.sumOf { (it.unrealizedPnL ?: 0.0).coerceAtMost(0.0).absoluteValue }
    return if (totalLoss == 0.0) {
        if (totalProfit > 0) "∞" else "N/A"
    } else {
        String.format("%.2f", totalProfit / totalLoss)
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
                        color = if (it >= 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
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
