package com.binancebot.mobile.presentation.screens.risk

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
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
// Reports Tab
@Composable
fun ReportsTab(
    dailyReport: com.binancebot.mobile.data.remote.dto.RiskReportDto?,
    weeklyReport: com.binancebot.mobile.data.remote.dto.RiskReportDto?,
    uiState: RiskManagementUiState,
    viewModel: RiskManagementViewModel,
    accountId: String?
) {
    var reportType by remember { mutableStateOf<String?>(null) }
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(Spacing.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            Button(
                onClick = {
                    reportType = "daily"
                    viewModel.loadDailyReport(accountId)
                },
                modifier = Modifier.weight(1f),
                enabled = uiState !is RiskManagementUiState.Loading
            ) {
                Text("Daily Report")
            }
            Button(
                onClick = {
                    reportType = "weekly"
                    viewModel.loadWeeklyReport(accountId)
                },
                modifier = Modifier.weight(1f),
                enabled = uiState !is RiskManagementUiState.Loading
            ) {
                Text("Weekly Report")
            }
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
                    onRetry = {
                        when (reportType) {
                            "daily" -> viewModel.loadDailyReport(accountId)
                            "weekly" -> viewModel.loadWeeklyReport(accountId)
                            else -> {}
                        }
                    },
                    modifier = Modifier.fillMaxSize()
                )
            }
            else -> {
                val report = when (reportType) {
                    "daily" -> dailyReport
                    "weekly" -> weeklyReport
                    else -> null
                }
                
                if (report != null) {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        item {
                            RiskReportCard(report = report, reportType = reportType ?: "")
                        }
                    }
                } else {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        EmptyStateCard(message = "Select a report type to view")
                    }
                }
            }
        }
    }
}

@Composable
private fun RiskReportCard(
    report: com.binancebot.mobile.data.remote.dto.RiskReportDto,
    reportType: String
) {
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
                text = if (reportType == "daily") {
                    "Daily Risk Report - ${report.date ?: "N/A"}"
                } else {
                    "Weekly Risk Report - ${report.weekStart ?: "N/A"} to ${report.weekEnd ?: "N/A"}"
                },
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            
            report.totalTrades?.let {
                MetricRow("Total Trades", it.toString())
            }
            report.winRate?.let { winRate ->
                val percentage = if (winRate > 1.0) winRate else winRate * 100
                MetricRow("Win Rate", "${String.format("%.2f", percentage)}%")
            }
            report.totalPnL?.let {
                MetricRow(
                    "Total PnL",
                    FormatUtils.formatCurrency(it),
                    valueColor = if (it >= 0) MaterialTheme.colorScheme.primary 
                    else MaterialTheme.colorScheme.error
                )
            }
            report.profitFactor?.let {
                MetricRow("Profit Factor", String.format("%.2f", it))
            }
            report.maxDrawdownPct?.let { drawdown ->
                val percentage = if (drawdown > 1.0) drawdown else drawdown * 100
                MetricRow("Max Drawdown", "${String.format("%.2f", percentage)}%")
            }
            report.sharpeRatio?.let {
                MetricRow("Sharpe Ratio", String.format("%.2f", it))
            }
            if (reportType == "daily") {
                report.dailyLoss?.let {
                    MetricRow("Daily Loss", FormatUtils.formatCurrency(it))
                }
            } else {
                report.weeklyLoss?.let {
                    MetricRow("Weekly Loss", FormatUtils.formatCurrency(it))
                }
            }
        }
    }
}
