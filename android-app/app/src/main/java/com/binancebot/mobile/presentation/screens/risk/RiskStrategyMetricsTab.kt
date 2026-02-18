package com.binancebot.mobile.presentation.screens.risk

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.RiskManagementViewModel
import com.binancebot.mobile.presentation.viewmodel.RiskManagementUiState
// Strategy Metrics Tab
@Composable
fun StrategyMetricsTab(
    strategyMetrics: List<com.binancebot.mobile.data.remote.dto.StrategyRiskMetricsDto>,
    uiState: RiskManagementUiState,
    viewModel: RiskManagementViewModel,
    accountId: String?
) {
    LaunchedEffect(accountId) {
        viewModel.loadAllStrategyMetrics(accountId)
    }
    
    when (uiState) {
        is RiskManagementUiState.Loading -> {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        }
        is RiskManagementUiState.Error -> {
            ErrorHandler(
                message = (uiState as RiskManagementUiState.Error).message,
                onRetry = { viewModel.loadAllStrategyMetrics(accountId) },
                modifier = Modifier.fillMaxSize()
            )
        }
        else -> {
            if (strategyMetrics.isEmpty()) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    EmptyStateCard(message = "No strategy metrics available")
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(horizontal = Spacing.ScreenPadding, vertical = Spacing.ScreenPadding),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    items(
                        items = strategyMetrics,
                        key = { it.strategyId }
                    ) { strategyMetric ->
                        StrategyRiskMetricCard(
                            strategyMetric = strategyMetric,
                            viewModel = viewModel
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StrategyRiskMetricCard(
    strategyMetric: com.binancebot.mobile.data.remote.dto.StrategyRiskMetricsDto,
    viewModel: RiskManagementViewModel
) {
    var showConfigDialog by remember { mutableStateOf(false) }
    
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.CardPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = strategyMetric.strategyName?.takeIf { it.isNotBlank() } 
                            ?: strategyMetric.strategyId,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    strategyMetric.symbol?.let {
                        Text(
                            text = it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                Button(
                    onClick = { showConfigDialog = true },
                    modifier = Modifier.height(36.dp)
                ) {
                    Text("Risk Config", style = MaterialTheme.typography.labelSmall)
                }
            }
            
            HorizontalDivider()
            
            strategyMetric.metrics?.let { metrics ->
                // Row 1: Total Trades, Win Rate (matching web app)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    RiskMetricCard(
                        label = "Total Trades",
                        value = metrics.totalTrades?.toString() ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                    RiskMetricCard(
                        label = "Win Rate",
                        value = metrics.winRate?.let { winRate ->
                            // API returns win_rate as percentage (e.g., 36.11), not decimal (0.3611)
                            val percentage = if (winRate > 1.0) winRate else winRate * 100
                            "${String.format("%.2f", percentage)}%"
                        } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                }
                
                // Row 2: Total PnL, Max Drawdown (matching web app)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    val totalPnL = metrics.totalPnL ?: ((metrics.dailyPnLUsdt ?: 0.0) + (metrics.weeklyPnLUsdt ?: 0.0))
                    RiskMetricCard(
                        label = "Total PnL",
                        value = if (totalPnL != 0.0) FormatUtils.formatCurrency(totalPnL) else "N/A",
                        valueColor = if (totalPnL != 0.0) {
                            if (totalPnL >= 0) MaterialTheme.colorScheme.primary 
                            else MaterialTheme.colorScheme.error
                        } else null,
                        modifier = Modifier.weight(1f)
                    )
                    RiskMetricCard(
                        label = "Max Drawdown",
                        value = metrics.maxDrawdownPct?.let { drawdown ->
                            // API returns max_drawdown_pct as percentage (e.g., 2.18), not decimal (0.0218)
                            val percentage = if (drawdown > 1.0) drawdown else drawdown * 100
                            "${String.format("%.2f", percentage)}%"
                        } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                }
                
                // Additional metrics (matching web app)
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                metrics.profitFactor?.let {
                    MetricRow("Profit Factor", String.format("%.2f", it))
                }
                metrics.sharpeRatio?.let {
                    MetricRow("Sharpe Ratio", String.format("%.2f", it))
                }
            } ?: run {
                Text(
                    text = strategyMetric.message ?: "No metrics available",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
    
    if (showConfigDialog) {
        StrategyRiskConfigDialog(
            strategyId = strategyMetric.strategyId,
            strategyName = strategyMetric.strategyName,
            onDismiss = { showConfigDialog = false },
            viewModel = viewModel
        )
    }
}
