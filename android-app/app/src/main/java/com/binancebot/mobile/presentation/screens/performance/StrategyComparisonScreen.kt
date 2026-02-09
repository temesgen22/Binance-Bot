package com.binancebot.mobile.presentation.screens.performance

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.StrategyPerformanceViewModel
import com.binancebot.mobile.presentation.viewmodel.StrategyPerformanceUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StrategyComparisonScreen(
    strategyIds: List<String>,
    navController: NavController,
    viewModel: StrategyPerformanceViewModel = hiltViewModel()
) {
    val performanceList by viewModel.performanceList.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
    LaunchedEffect(Unit) {
        viewModel.loadPerformance()
    }
    
    // Get selected strategies
    val selectedStrategies = remember(performanceList, strategyIds) {
        performanceList?.strategies?.filter { it.strategyId in strategyIds } ?: emptyList()
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Strategy Comparison") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        when (uiState) {
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
                    message = (uiState as StrategyPerformanceUiState.Error).message,
                    onRetry = { viewModel.loadPerformance() },
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                )
            }
            else -> {
                if (selectedStrategies.isEmpty()) {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Icon(
                                Icons.Default.CompareArrows,
                                contentDescription = "No comparison",
                                modifier = Modifier.size(64.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(Spacing.Medium))
                            Text(
                                text = "No strategies selected",
                                style = MaterialTheme.typography.titleMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(Spacing.Small))
                            TextButton(onClick = { navController.popBackStack() }) {
                                Text("Go Back")
                            }
                        }
                    }
                } else {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding)
                            .verticalScroll(rememberScrollState())
                            .padding(Spacing.ScreenPadding),
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        // Comparison Header
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
                                Text(
                                    text = "Comparing ${selectedStrategies.size} Strategies",
                                    style = MaterialTheme.typography.titleLarge,
                                    fontWeight = FontWeight.Bold
                                )
                                Text(
                                    text = "Side-by-side performance comparison",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                        
                        // Comparison Table
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
                                Text(
                                    text = "Performance Metrics",
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.Bold
                                )
                                Divider()
                                
                                // Strategy Names Row
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                                ) {
                                    Column(
                                        modifier = Modifier.weight(1f)
                                    ) {
                                        Text(
                                            text = "Metric",
                                            style = MaterialTheme.typography.labelMedium,
                                            fontWeight = FontWeight.Bold
                                        )
                                    }
                                    selectedStrategies.forEach { strategy ->
                                        Column(
                                            modifier = Modifier.weight(1f),
                                            horizontalAlignment = Alignment.CenterHorizontally
                                        ) {
                                            Text(
                                                text = strategy.strategyName,
                                                style = MaterialTheme.typography.labelSmall,
                                                fontWeight = FontWeight.Bold
                                            )
                                            Text(
                                                text = strategy.symbol,
                                                style = MaterialTheme.typography.bodySmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                        }
                                    }
                                }
                                
                                Divider()
                                
                                // Metrics Rows
                                ComparisonMetricRow("Total PnL", selectedStrategies.map { FormatUtils.formatCurrency(it.totalPnl) })
                                ComparisonMetricRow("Win Rate", selectedStrategies.map { String.format("%.1f%%", it.winRate * 100) })
                                ComparisonMetricRow("Total Trades", selectedStrategies.map { it.totalTrades.toString() })
                                ComparisonMetricRow("Completed Trades", selectedStrategies.map { it.completedTrades.toString() })
                                ComparisonMetricRow("Winning Trades", selectedStrategies.map { it.winningTrades.toString() })
                                ComparisonMetricRow("Losing Trades", selectedStrategies.map { it.losingTrades.toString() })
                                ComparisonMetricRow("Avg Profit/Trade", selectedStrategies.map { FormatUtils.formatCurrency(it.avgProfitPerTrade) })
                                ComparisonMetricRow("Largest Win", selectedStrategies.map { FormatUtils.formatCurrency(it.largestWin) })
                                ComparisonMetricRow("Largest Loss", selectedStrategies.map { FormatUtils.formatCurrency(it.largestLoss) })
                                ComparisonMetricRow("Leverage", selectedStrategies.map { "${it.leverage}x" })
                                ComparisonMetricRow("Risk/Trade", selectedStrategies.map { String.format("%.2f%%", it.riskPerTrade * 100) })
                            }
                        }
                        
                        // Strategy Details Cards
                        selectedStrategies.forEach { strategy ->
                            Card(
                                modifier = Modifier.fillMaxWidth(),
                                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
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
                                        Column {
                                            Text(
                                                text = strategy.strategyName,
                                                style = MaterialTheme.typography.titleMedium,
                                                fontWeight = FontWeight.Bold
                                            )
                                            Text(
                                                text = "${strategy.symbol} • ${strategy.strategyType}",
                                                style = MaterialTheme.typography.bodySmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                        }
                                        TextButton(onClick = {
                                            navController.navigate("strategy_details/${strategy.strategyId}")
                                        }) {
                                            Text("View Details")
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
fun ComparisonMetricRow(
    label: String,
    values: List<String>
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
    ) {
        Column(
            modifier = Modifier.weight(1f)
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        values.forEach { value ->
            Column(
                modifier = Modifier.weight(1f),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = value,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Bold
                )
            }
        }
    }
}


