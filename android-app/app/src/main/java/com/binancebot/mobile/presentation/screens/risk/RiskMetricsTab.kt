package com.binancebot.mobile.presentation.screens.risk

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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

// Portfolio Metrics Tab
@Composable
fun PortfolioMetricsTab(
    portfolioMetrics: com.binancebot.mobile.data.remote.dto.PortfolioRiskMetricsDto?,
    uiState: RiskManagementUiState,
    onRetry: () -> Unit,
    viewModel: RiskManagementViewModel,
    accountId: String?
) {
    LaunchedEffect(accountId) {
        viewModel.loadPortfolioMetrics(accountId)
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
                onRetry = onRetry,
                modifier = Modifier.fillMaxSize()
            )
        }
        else -> {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(Spacing.ScreenPadding),
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                if (portfolioMetrics == null) {
                    EmptyStateCard(message = "No portfolio metrics data available. Please refresh or check your account.")
                } else {
                    portfolioMetrics.let { metrics ->
                        // Balance Metrics
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
                            Text(
                                text = "Balance Metrics",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold
                            )
                            HorizontalDivider()
                            
                            (metrics.totalBalanceUsdt ?: metrics.currentBalance)?.let {
                                MetricRow("Total Balance", FormatUtils.formatCurrency(it))
                            }
                            metrics.availableBalanceUsdt?.let {
                                MetricRow("Available Balance", FormatUtils.formatCurrency(it))
                            }
                            metrics.usedMarginUsdt?.let {
                                MetricRow("Used Margin", FormatUtils.formatCurrency(it))
                            }
                            (metrics.peakBalanceUsdt ?: metrics.peakBalance)?.let {
                                MetricRow("Peak Balance", FormatUtils.formatCurrency(it))
                            }
                        }
                    }
                    
                    // Performance Metrics
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
                            Text(
                                text = "Performance Metrics",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold
                            )
                            HorizontalDivider()
                            
                            metrics.totalTrades?.let {
                                MetricRow("Total Trades", it.toString())
                            }
                            metrics.winningTrades?.let { wins ->
                                metrics.losingTrades?.let { losses ->
                                    MetricRow("Wins / Losses", "$wins / $losses")
                                }
                            }
                            metrics.winRate?.let { winRate ->
                                val percentage = if (winRate > 1.0) winRate else winRate * 100
                                MetricRow("Win Rate", "${String.format("%.2f", percentage)}%")
                            }
                            metrics.profitFactor?.let {
                                MetricRow("Profit Factor", String.format("%.2f", it))
                            }
                            metrics.sharpeRatio?.let {
                                MetricRow("Sharpe Ratio", String.format("%.2f", it))
                            }
                            metrics.avgWin?.let {
                                MetricRow("Avg Win", FormatUtils.formatCurrency(it))
                            }
                            metrics.avgLoss?.let {
                                MetricRow("Avg Loss", FormatUtils.formatCurrency(it))
                            }
                        }
                    }
                    
                    // Risk Metrics
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
                            Text(
                                text = "Risk Metrics",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold
                            )
                            HorizontalDivider()
                            
                            metrics.totalExposureUsdt?.let {
                                MetricRow("Total Exposure", FormatUtils.formatCurrency(it))
                            }
                            metrics.totalExposurePct?.let {
                                MetricRow("Exposure %", "${String.format("%.2f", it * 100)}%")
                            }
                            metrics.maxDrawdownPct?.let {
                                MetricRow("Max Drawdown", "${String.format("%.2f", it * 100)}%")
                            }
                            metrics.currentDrawdownPct?.let {
                                MetricRow("Current Drawdown", "${String.format("%.2f", it * 100)}%")
                            }
                            metrics.dailyPnLUsdt?.let {
                                MetricRow("Daily PnL", FormatUtils.formatCurrency(it))
                            }
                            metrics.weeklyPnLUsdt?.let {
                                MetricRow("Weekly PnL", FormatUtils.formatCurrency(it))
                            }
                        }
                    }
                    }
                }
            }
        }
    }
}
