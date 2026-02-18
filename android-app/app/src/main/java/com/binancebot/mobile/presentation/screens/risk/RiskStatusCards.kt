package com.binancebot.mobile.presentation.screens.risk

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.data.remote.dto.PortfolioRiskMetricsDto
import com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto
import com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils

/**
 * Status tab cards and MetricRow extracted from RiskManagementScreen (P1.1).
 * Used by PortfolioStatusTab.
 */

@Composable
fun RiskMetricRow(
    label: String,
    value: String,
    valueColor: androidx.compose.ui.graphics.Color? = null,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Bold,
            color = valueColor ?: MaterialTheme.colorScheme.onSurface
        )
    }
}

@Composable
fun StatusCard(status: PortfolioRiskStatusDto) {
    val statusColor = when (status.status?.lowercase() ?: "") {
        "active", "ok", "normal" -> MaterialTheme.colorScheme.primaryContainer
        "warning" -> MaterialTheme.colorScheme.errorContainer
        "breach", "paused", "no_config" -> MaterialTheme.colorScheme.error
        else -> MaterialTheme.colorScheme.surfaceVariant
    }
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
        colors = CardDefaults.cardColors(containerColor = statusColor)
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(Spacing.CardPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.surface) {
                    Text(
                        text = (status.status ?: "Unknown").uppercase(),
                        modifier = Modifier.padding(horizontal = Spacing.Medium, vertical = Spacing.Small),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            HorizontalDivider()
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)) {
                Text(
                    text = "Account: ${status.accountId ?: "All Accounts"}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    text = "Last Updated: ${java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date())}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
fun ProgressBarsCard(
    status: PortfolioRiskStatusDto,
    riskConfig: RiskManagementConfigDto? = null
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(Spacing.CardPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            Text(text = "Risk Limits Progress", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            HorizontalDivider()
            status.totalExposure?.let { exposure ->
                ProgressBarItem(
                    label = "Portfolio Exposure",
                    current = exposure,
                    limit = riskConfig?.maxPortfolioExposureUsdt,
                    unit = " USDT",
                    isNegative = false
                )
            }
            status.dailyPnL?.let { dailyPnL ->
                if (dailyPnL < 0) {
                    ProgressBarItem(
                        label = "Daily Loss",
                        current = Math.abs(dailyPnL),
                        limit = riskConfig?.maxDailyLossUsdt?.let { Math.abs(it) },
                        unit = " USDT",
                        isNegative = true
                    )
                }
            }
            status.weeklyPnL?.let { weeklyPnL ->
                if (weeklyPnL < 0) {
                    ProgressBarItem(
                        label = "Weekly Loss",
                        current = Math.abs(weeklyPnL),
                        limit = riskConfig?.maxWeeklyLossUsdt?.let { Math.abs(it) },
                        unit = " USDT",
                        isNegative = true
                    )
                }
            }
            status.currentDrawdownPct?.let { current ->
                val limit = status.maxDrawdownLimitPct ?: riskConfig?.maxDrawdownPct
                if (limit != null) {
                    ProgressBarItem(
                        label = "Drawdown",
                        current = current * 100,
                        limit = limit * 100,
                        unit = "%",
                        isNegative = false
                    )
                }
            }
        }
    }
}

@Composable
private fun ProgressBarItem(
    label: String,
    current: Double,
    limit: Double?,
    unit: String,
    isNegative: Boolean
) {
    if (limit == null || limit == 0.0) {
        RiskMetricRow(
            label = label,
            value = "${String.format("%.2f", current)}$unit",
            modifier = Modifier.padding(vertical = Spacing.Small)
        )
        return
    }
    val percentage = when {
        isNegative && limit < 0 -> Math.abs((current / limit) * 100)
        !isNegative && limit > 0 -> (current / limit) * 100
        else -> 0.0
    }.coerceIn(0.0, 100.0)
    val barColor = when {
        percentage >= 90 -> MaterialTheme.colorScheme.error
        percentage >= 80 -> androidx.compose.ui.graphics.Color(0xFFFFC107)
        percentage >= 60 -> androidx.compose.ui.graphics.Color(0xFFFF9800)
        else -> MaterialTheme.colorScheme.primary
    }
    Column(
        modifier = Modifier.fillMaxWidth().padding(vertical = Spacing.Small),
        verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(text = label, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold)
            Text(
                text = "${String.format("%.2f", current)}$unit / ${String.format("%.2f", limit)}$unit (${String.format("%.0f", percentage)}%)",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        LinearProgressIndicator(
            progress = { (percentage / 100).toFloat() },
            modifier = Modifier.fillMaxWidth().height(8.dp),
            color = barColor,
            trackColor = MaterialTheme.colorScheme.surfaceVariant
        )
    }
}

@Composable
fun MetricsGridCard(
    status: PortfolioRiskStatusDto,
    portfolioMetrics: PortfolioRiskMetricsDto? = null
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(Spacing.CardPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            Text(text = "Key Metrics", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            HorizontalDivider()
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.Small)) {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)) {
                    RiskMetricCard(
                        label = "Total PnL",
                        value = portfolioMetrics?.let { metrics ->
                            metrics.totalPnL?.let { FormatUtils.formatCurrency(it) }
                                ?: run {
                                    val totalPnL = (metrics.dailyPnLUsdt ?: 0.0) + (metrics.weeklyPnLUsdt ?: 0.0)
                                    if (totalPnL != 0.0) FormatUtils.formatCurrency(totalPnL) else "N/A"
                                }
                        } ?: status.dailyPnL?.let { FormatUtils.formatCurrency(it) } ?: "N/A",
                        valueColor = portfolioMetrics?.let { metrics ->
                            metrics.totalPnL?.let { if (it >= 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error }
                                ?: run {
                                    val totalPnL = (metrics.dailyPnLUsdt ?: 0.0) + (metrics.weeklyPnLUsdt ?: 0.0)
                                    if (totalPnL != 0.0) {
                                        if (totalPnL >= 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                                    } else null
                                }
                        } ?: status.dailyPnL?.let { if (it >= 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error },
                        modifier = Modifier.weight(1f)
                    )
                    RiskMetricCard(
                        label = "Win Rate",
                        value = portfolioMetrics?.winRate?.let { wr -> val pct = if (wr > 1.0) wr else wr * 100; "${String.format("%.2f", pct)}%" } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                }
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)) {
                    RiskMetricCard(label = "Profit Factor", value = portfolioMetrics?.profitFactor?.let { String.format("%.2f", it) } ?: "N/A", modifier = Modifier.weight(1f))
                    RiskMetricCard(label = "Sharpe Ratio", value = portfolioMetrics?.sharpeRatio?.let { String.format("%.2f", it) } ?: "N/A", modifier = Modifier.weight(1f))
                }
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)) {
                    RiskMetricCard(
                        label = "Max Drawdown",
                        value = status.maxDrawdownPct?.let { "${String.format("%.2f", it * 100)}%" }
                            ?: portfolioMetrics?.maxDrawdownPct?.let { "${String.format("%.2f", it * 100)}%" } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                    RiskMetricCard(
                        label = "Current Balance",
                        value = portfolioMetrics?.let { (it.totalBalanceUsdt ?: it.currentBalance)?.let { FormatUtils.formatCurrency(it) } ?: "N/A" } ?: "N/A",
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }
    }
}

@Composable
fun RiskMetricCard(
    label: String,
    value: String,
    valueColor: androidx.compose.ui.graphics.Color? = null,
    modifier: Modifier = Modifier
) {
    Column(modifier = modifier) {
        Text(text = label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(text = value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = valueColor ?: MaterialTheme.colorScheme.onSurface)
    }
}

@Composable
fun WarningsCard(warnings: List<String>, circuitBreakers: List<String>) {
    if (warnings.isEmpty() && circuitBreakers.isEmpty()) return
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(Spacing.CardPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            if (warnings.isNotEmpty()) {
                Text(text = "Warnings", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onErrorContainer)
                warnings.forEach { Text(text = "- $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onErrorContainer, modifier = Modifier.padding(start = Spacing.Small)) }
            }
            if (circuitBreakers.isNotEmpty()) {
                if (warnings.isNotEmpty()) HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                Text(text = "Active Circuit Breakers", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onErrorContainer)
                circuitBreakers.forEach { Text(text = "- $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onErrorContainer, modifier = Modifier.padding(start = Spacing.Small)) }
            }
        }
    }
}

@Composable
fun EmptyStateCard(message: String) {
    Card(modifier = Modifier.fillMaxWidth(), elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(Spacing.Large),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(text = message, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
