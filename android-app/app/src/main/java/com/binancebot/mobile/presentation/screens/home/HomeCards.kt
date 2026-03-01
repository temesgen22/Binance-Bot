package com.binancebot.mobile.presentation.screens.home

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.presentation.components.StatusBadge
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.domain.model.Account
import com.binancebot.mobile.domain.model.Strategy
import com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto
import com.binancebot.mobile.data.remote.dto.StrategyHealthDto
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto
import com.binancebot.mobile.data.remote.dto.SymbolPnLDto

@Composable
internal fun QuickStatCard(
    title: String,
    value: String,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
    ) {
        Column(
            modifier = Modifier.padding(Spacing.Medium),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(modifier = Modifier.height(Spacing.Small))
            Text(
                text = value,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
internal fun QuickActionButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    OutlinedButton(
        onClick = onClick,
        modifier = modifier
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.bodySmall
        )
    }
}

@Composable
internal fun RiskStatusBanner(
    riskStatus: String?,
    accountCount: Int,
    onClick: () -> Unit
) {
    val status = riskStatus?.lowercase() ?: "active"
    
    val bgColor: Color
    val textColor: Color
    val icon: androidx.compose.ui.graphics.vector.ImageVector
    val message: String
    
    when (status) {
        "breach", "paused" -> {
            bgColor = MaterialTheme.colorScheme.errorContainer
            textColor = MaterialTheme.colorScheme.onErrorContainer
            icon = Icons.Default.Warning
            message = if (accountCount > 0) "$accountCount account(s) in breach" else "Portfolio breach detected"
        }
        "warning" -> {
            bgColor = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.7f)
            textColor = MaterialTheme.colorScheme.onErrorContainer
            icon = Icons.Default.Warning
            message = if (accountCount > 0) "$accountCount account(s) in warning" else "Portfolio warning"
        }
        else -> return // Don't show banner if status is active/normal
    }
    
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = bgColor)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Medium),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = textColor,
                modifier = Modifier.size(24.dp)
            )
            Text(
                text = message,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = textColor,
                modifier = Modifier.weight(1f)
            )
            Icon(
                imageVector = Icons.Default.ChevronRight,
                contentDescription = "View Details",
                tint = textColor
            )
        }
    }
}

@Composable
internal fun TotalPnLHeroCard(
    totalPnL: Double,
    realizedPnL: Double,
    unrealizedPnL: Double,
    pnlChange24h: Double?
) {
    val isPositive = totalPnL >= 0
    val gradientColors = if (isPositive) {
        listOf(
            androidx.compose.ui.graphics.Color(0xFF4CAF50),
            androidx.compose.ui.graphics.Color(0xFF66BB6A)
        )
    } else {
        listOf(
            androidx.compose.ui.graphics.Color(0xFFF44336),
            androidx.compose.ui.graphics.Color(0xFFE57373)
        )
    }
    
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.large
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    brush = androidx.compose.ui.graphics.Brush.horizontalGradient(gradientColors)
                )
                .padding(Spacing.Large)
        ) {
            Column(
                verticalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                Text(
                    text = "Total PnL",
                    style = MaterialTheme.typography.titleMedium,
                    color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.9f)
                )
                Text(
                    text = FormatUtils.formatCurrency(totalPnL),
                    style = MaterialTheme.typography.displaySmall,
                    fontWeight = FontWeight.Bold,
                    color = androidx.compose.ui.graphics.Color.White
                )
                if (pnlChange24h != null) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(Spacing.Tiny),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = if (pnlChange24h >= 0) Icons.Default.TrendingUp else Icons.Default.TrendingDown,
                            contentDescription = null,
                            tint = androidx.compose.ui.graphics.Color.White,
                            modifier = Modifier.size(16.dp)
                        )
                        Text(
                            text = "${if (pnlChange24h >= 0) "+" else ""}${FormatUtils.formatCurrency(pnlChange24h)} (24h)",
                            style = MaterialTheme.typography.bodyMedium,
                            color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.9f)
                        )
                    }
                }
                Row(
                    modifier = Modifier.padding(top = Spacing.Small),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    Column {
                        Text(
                            text = "Realized",
                            style = MaterialTheme.typography.bodySmall,
                            color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.8f)
                        )
                        Text(
                            text = FormatUtils.formatCurrency(realizedPnL),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            color = androidx.compose.ui.graphics.Color.White
                        )
                    }
                    Column {
                        Text(
                            text = "Unrealized",
                            style = MaterialTheme.typography.bodySmall,
                            color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.8f)
                        )
                        Text(
                            text = FormatUtils.formatCurrency(unrealizedPnL),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            color = androidx.compose.ui.graphics.Color.White
                        )
                    }
                }
            }
        }
    }
}

@Composable
internal fun KeyMetricsGrid(
    totalPnL: Double,
    winRate: Double,
    totalTrades: Int,
    activeStrategies: Int,
    accountBalance: Double?,
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
            MetricCard(
                title = "Total PnL",
                value = FormatUtils.formatCurrency(totalPnL),
                icon = Icons.Default.AccountBalance,
                isPositive = totalPnL >= 0,
                modifier = Modifier.weight(1f)
            )
            MetricCard(
                title = "Win Rate",
                value = String.format("%.1f%%", if (winRate > 1.0) winRate else winRate * 100),
                icon = Icons.Default.CheckCircle,
                modifier = Modifier.weight(1f)
            )
        }
        // Row 2
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            MetricCard(
                title = "Total Trades",
                value = totalTrades.toString(),
                icon = Icons.Default.SwapHoriz,
                modifier = Modifier.weight(1f)
            )
            MetricCard(
                title = "Active",
                value = activeStrategies.toString(),
                icon = Icons.Default.PlayArrow,
                modifier = Modifier.weight(1f)
            )
        }
        // Row 3
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            accountBalance?.let {
                MetricCard(
                    title = "Balance",
                    value = FormatUtils.formatCurrency(it),
                    icon = Icons.Default.AccountBalanceWallet,
                    modifier = Modifier.weight(1f)
                )
            }
            profitFactor?.let {
                MetricCard(
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
internal fun MetricCard(
    title: String,
    value: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    modifier: Modifier = Modifier,
    isPositive: Boolean? = null
) {
    Card(modifier = modifier) {
        Column(
            modifier = Modifier.padding(Spacing.Medium),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = if (isPositive != null) {
                    if (isPositive) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                },
                modifier = Modifier.size(24.dp)
            )
            Spacer(modifier = Modifier.height(Spacing.Small))
            Text(
                text = title,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                text = value,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = if (isPositive != null) {
                    if (isPositive) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.onSurface
                }
            )
        }
    }
}

@Composable
internal fun AccountRiskAlertsCard(
    accounts: List<com.binancebot.mobile.domain.model.Account>,
    riskStatus: com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto?,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f)
        )
    ) {
        Column(
            modifier = Modifier.padding(Spacing.Medium),
            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Default.Warning,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.error,
                    modifier = Modifier.size(20.dp)
                )
                Text(
                    text = "Account Risk Alerts",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.error
                )
            }
            riskStatus?.status?.let { status ->
                Text(
                    text = "Status: ${status.uppercase()}",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold
                )
            }
            riskStatus?.warnings?.forEach { warning ->
                Text(
                    text = "- $warning",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Text(
                text = "Tap to view details ->",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(top = Spacing.Small)
            )
        }
    }
}

@Composable
internal fun StrategyHealthAlertsCard(
    strategies: List<com.binancebot.mobile.domain.model.Strategy>,
    strategyHealth: Map<String, com.binancebot.mobile.data.remote.dto.StrategyHealthDto?>,
    onClick: (String) -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f)
        )
    ) {
        Column(
            modifier = Modifier.padding(Spacing.Medium),
            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Default.Warning,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.error,
                    modifier = Modifier.size(20.dp)
                )
                Text(
                    text = "Strategy Health Issues (${strategies.size})",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.error
                )
            }
            strategies.take(3).forEach { strategy ->
                val health = strategyHealth[strategy.id]
                val healthStatus = health?.healthStatus
                val orderFailureReason = health?.orderFailure?.reason
                val statusText = when {
                    !orderFailureReason.isNullOrBlank() -> "Order not executed: ${orderFailureReason.take(40)}${if (orderFailureReason.length > 40) "…" else ""}"
                    healthStatus == "execution_stale" -> "Stale"
                    healthStatus == "task_dead" -> "Dead"
                    healthStatus == "no_recent_orders" -> "No Orders"
                    else -> "Issue"
                }
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onClick(strategy.id) },
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = strategy.name,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                        Text(
                            text = "${strategy.symbol}  |  $statusText",
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
                if (strategy != strategies.take(3).last()) {
                    HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Tiny))
                }
            }
            if (strategies.size > 3) {
                Text(
                    text = "And ${strategies.size - 3} more...",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = Spacing.Small)
                )
            }
        }
    }
}

@Composable
internal fun PnLChartSection(
    pnlTimeline: List<Map<String, Any>>?,
    totalPnL: Double
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(Spacing.Medium),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "PnL Timeline",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                // Time period selector would go here
            }
            
            if (pnlTimeline.isNullOrEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(200.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                    ) {
                        Icon(
                            imageVector = Icons.Default.ShowChart,
                            contentDescription = null,
                            modifier = Modifier.size(48.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                        )
                        Text(
                            text = "Chart data not available",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "Total PnL: ${FormatUtils.formatCurrency(totalPnL)}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            } else {
                // TODO: Implement actual chart using chart library
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(200.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "Chart implementation pending",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

@Composable
internal fun QuickStatsGrid(
    bestStrategy: com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto?,
    worstStrategy: com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto?,
    topSymbol: com.binancebot.mobile.data.remote.dto.SymbolPnLDto?,
    completedTrades: Int
) {
    Column(
        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            bestStrategy?.let {
                QuickStatCard(
                    title = "Best Strategy",
                    value = "${it.strategyName}\n${FormatUtils.formatCurrency(it.totalPnl)}",
                    modifier = Modifier.weight(1f)
                )
            }
            worstStrategy?.let {
                QuickStatCard(
                    title = "Worst Strategy",
                    value = "${it.strategyName}\n${FormatUtils.formatCurrency(it.totalPnl)}",
                    modifier = Modifier.weight(1f)
                )
            }
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            topSymbol?.let {
                QuickStatCard(
                    title = "Top Symbol",
                    value = "${it.symbol}\n${FormatUtils.formatCurrency(it.totalPnL)}",
                    modifier = Modifier.weight(1f)
                )
            }
            QuickStatCard(
                title = "Completed",
                value = completedTrades.toString(),
                modifier = Modifier.weight(1f)
            )
        }
    }
}

@Composable
internal fun EnhancedStrategyCard(
    strategy: com.binancebot.mobile.domain.model.Strategy,
    strategyHealth: com.binancebot.mobile.data.remote.dto.StrategyHealthDto?,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
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
                    text = "${strategy.symbol}  |  ${strategy.strategyType}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(modifier = Modifier.height(Spacing.Small))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    StatusBadge(status = strategy.status)
                    // Health indicator
                    strategyHealth?.let { health ->
                        val healthStatus = health.healthStatus
                        val hasOrderFailure = health.orderFailure?.reason != null
                        if (hasOrderFailure || healthStatus in listOf("execution_stale", "task_dead", "no_recent_orders")) {
                            val (iconVector, color) = when {
                                hasOrderFailure -> Icons.Default.Warning to MaterialTheme.colorScheme.errorContainer
                                healthStatus == "execution_stale" -> Icons.Default.Warning to MaterialTheme.colorScheme.error
                                healthStatus == "task_dead" -> Icons.Default.Cancel to MaterialTheme.colorScheme.error
                                healthStatus == "no_recent_orders" -> Icons.Default.Warning to MaterialTheme.colorScheme.errorContainer
                                else -> Icons.Default.Help to MaterialTheme.colorScheme.onSurfaceVariant
                            }
                            Box(
                                modifier = Modifier.size(20.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(
                                    imageVector = iconVector,
                                    contentDescription = when {
                                        hasOrderFailure -> "Order not executed"
                                        healthStatus == "execution_stale" -> "Stale"
                                        healthStatus == "task_dead" -> "Dead"
                                        healthStatus == "no_recent_orders" -> "No orders"
                                        else -> "Health"
                                    },
                                    tint = color,
                                    modifier = Modifier.size(18.dp)
                                )
                            }
                        }
                    }
                    Text(
                        text = "| PnL: ${FormatUtils.formatCurrency(strategy.unrealizedPnL ?: 0.0)}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            Icon(
                imageVector = Icons.Default.ChevronRight,
                contentDescription = "View Details",
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}
