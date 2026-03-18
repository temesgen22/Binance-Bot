package com.binancebot.mobile.presentation.screens.strategies

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.data.remote.dto.StrategyHealthDto
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto
import com.binancebot.mobile.presentation.components.StatusBadge
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.util.AppLogger
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import java.util.Locale

@Composable
fun EnhancedStrategyCard(
    performance: StrategyPerformanceDto,
    isExpanded: Boolean,
    onExpandToggle: () -> Unit,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onCopy: () -> Unit,
    onDelete: () -> Unit,
    onDetails: () -> Unit,
    strategyHealthFlow: Flow<StrategyHealthDto?>,
    onLoadStrategyHealth: (String) -> Unit,
    strategyRiskConfig: com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto?,
    isLoadingRisk: Boolean,
    onLoadRiskConfig: () -> Unit,
    onCreateRiskConfig: (com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto) -> Unit,
    onUpdateRiskConfig: (com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto) -> Unit,
    isActionLoading: Boolean = false
) {
    val health by strategyHealthFlow.collectAsState(initial = null)
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
            // Header with Rank
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(onClick = onDetails),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.weight(1f)
                ) {
                    // Rank Badge
                    RankBadge(rank = performance.rank ?: 0)
                    
                    Column(
                        modifier = Modifier
                            .weight(1f)
                            .padding(end = Spacing.Small)
                    ) {
                        Text(
                            text = performance.strategyName,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                            lineHeight = MaterialTheme.typography.titleMedium.lineHeight * 0.9
                        )
                        Spacer(modifier = Modifier.height(2.dp))
                        Text(
                            text = "${performance.symbol}  |  ${performance.strategyType}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
                
                // Right side: Status, Health Indicator, Expand button
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Tiny),
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.wrapContentWidth()
                ) {
                    StatusBadge(status = performance.status)
                    // Health indicator for running strategies - always visible next to status
                    val isRunning = performance.status.lowercase().trim() == "running"
                    if (isRunning) {
                        Spacer(modifier = Modifier.width(4.dp))
                        StrategyHealthIndicator(
                            strategyId = performance.strategyId,
                            health = health,
                            onLoadHealth = { onLoadStrategyHealth(performance.strategyId) },
                            loadWhenVisible = isExpanded
                        )
                    }
                }
                IconButton(onClick = onExpandToggle) {
                    Icon(
                        if (isExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                        contentDescription = if (isExpanded) "Collapse" else "Expand"
                    )
                }
            }
            
            // Key Metrics Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                MetricColumn("Total PnL", FormatUtils.formatCurrency(performance.totalPnl), performance.totalPnl >= 0)
                MetricColumn("Win Rate", "${String.format("%.2f", performance.winRate)}%")
                MetricColumn("Trades", "${performance.completedTrades}/${performance.totalTrades}")
            }
            
            // Second Metrics Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                MetricColumn("Realized", FormatUtils.formatCurrency(performance.totalRealizedPnl), performance.totalRealizedPnl >= 0)
                MetricColumn("Unrealized", FormatUtils.formatCurrency(performance.totalUnrealizedPnl), performance.totalUnrealizedPnl >= 0)
                performance.percentile?.let {
                    PercentileBadge(percentile = it)
                }
            }
            
            // Position Info (if has position)
            if (performance.positionSide != null && performance.positionSize != null && performance.positionSize > 0) {
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Default.ShowChart,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp),
                            tint = MaterialTheme.colorScheme.primary
                        )
                        Text(
                            text = "${performance.positionSide}  |  ${String.format("%.4f", performance.positionSize)}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.primary,
                            fontWeight = FontWeight.Medium
                        )
                    }
                    performance.totalUnrealizedPnl?.let { pnl ->
                        Text(
                            text = FormatUtils.formatCurrency(pnl),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            color = if (pnl >= 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                        )
                    }
                }
            }
            
            // Expanded Details
            AnimatedVisibility(
                visible = isExpanded,
                enter = expandVertically(),
                exit = shrinkVertically()
            ) {
                StrategyDetailsView(
                    performance = performance,
                    strategyHealth = health,
                    onLoadStrategyHealth = { onLoadStrategyHealth(performance.strategyId) },
                    strategyRiskConfig = strategyRiskConfig,
                    isLoadingRisk = isLoadingRisk,
                    onLoadRiskConfig = onLoadRiskConfig,
                    onCreateRiskConfig = onCreateRiskConfig,
                    onUpdateRiskConfig = onUpdateRiskConfig
                )
            }
            
            Divider(modifier = Modifier.padding(vertical = Spacing.Small))
            
            // Actions
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                // Only show Start button if not stopped_by_risk (user can't start if stopped by risk)
                if (performance.status == "running") {
                    Button(
                        onClick = onStop,
                        modifier = Modifier.weight(1f),
                        enabled = !isActionLoading,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.error
                        )
                    ) {
                        if (isActionLoading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                color = MaterialTheme.colorScheme.onError,
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        } else {
                            Icon(Icons.Default.Stop, null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        }
                        Text(if (isActionLoading) "Stopping..." else "Stop")
                    }
                } else if (performance.status != "stopped_by_risk") {
                    Button(
                        onClick = onStart,
                        modifier = Modifier.weight(1f),
                        enabled = !isActionLoading,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.primary
                        )
                    ) {
                        if (isActionLoading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                color = MaterialTheme.colorScheme.onPrimary,
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        } else {
                            Icon(Icons.Default.PlayArrow, null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        }
                        Text(if (isActionLoading) "Starting..." else "Start")
                    }
                } else {
                    // Show disabled button for stopped_by_risk
                    Button(
                        onClick = { },
                        modifier = Modifier.weight(1f),
                        enabled = false,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        )
                    ) {
                        Icon(Icons.Default.Warning, null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        Text("Stopped by Risk")
                    }
                }
                IconButton(onClick = onCopy) {
                    Icon(Icons.Default.ContentCopy, "Copy", tint = MaterialTheme.colorScheme.primary)
                }
                IconButton(onClick = onDelete) {
                    Icon(Icons.Default.Delete, "Delete", tint = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}

@Composable
fun RankBadge(rank: Int) {
    val (backgroundColor, textColor) = when (rank) {
        1 -> Pair(Color(0xFFFFD700), Color(0xFF333333)) // Gold
        2 -> Pair(Color(0xFFC0C0C0), Color(0xFF333333)) // Silver
        3 -> Pair(Color(0xFFCD7F32), Color.White) // Bronze
        else -> Pair(MaterialTheme.colorScheme.surfaceVariant, MaterialTheme.colorScheme.onSurfaceVariant)
    }
    
    Surface(
        modifier = Modifier.size(40.dp),
        shape = MaterialTheme.shapes.medium,
        color = backgroundColor
    ) {
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier.fillMaxSize()
        ) {
            Text(
                text = "$rank",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = textColor
            )
        }
    }
}

@Composable
fun PercentileBadge(percentile: Double) {
    val (backgroundColor, textColor) = when {
        percentile >= 75 -> Pair(
            MaterialTheme.colorScheme.primaryContainer,
            MaterialTheme.colorScheme.onPrimaryContainer
        )
        percentile >= 50 -> Pair(
            MaterialTheme.colorScheme.secondaryContainer,
            MaterialTheme.colorScheme.onSecondaryContainer
        )
        else -> Pair(
            MaterialTheme.colorScheme.errorContainer,
            MaterialTheme.colorScheme.onErrorContainer
        )
    }
    
    Surface(
        shape = MaterialTheme.shapes.small,
        color = backgroundColor
    ) {
        Text(
            text = "${percentile.toInt()}%",
            style = MaterialTheme.typography.labelSmall,
            color = textColor,
            modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny)
        )
    }
}

@Composable
fun MetricColumn(label: String, value: String, isPositive: Boolean = false) {
    Column {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Bold,
            color = if (isPositive && value.startsWith("-").not()) {
                MaterialTheme.colorScheme.primary
            } else if (value.startsWith("-")) {
                MaterialTheme.colorScheme.error
            } else {
                MaterialTheme.colorScheme.onSurface
            }
        )
    }
}

@Composable
fun StrategyDetailsView(
    performance: StrategyPerformanceDto,
    strategyHealth: StrategyHealthDto?,
    onLoadStrategyHealth: () -> Unit,
    strategyRiskConfig: com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto?,
    isLoadingRisk: Boolean,
    onLoadRiskConfig: () -> Unit,
    onCreateRiskConfig: (com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto) -> Unit,
    onUpdateRiskConfig: (com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto) -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = Spacing.Small),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
    ) {
        // Performance Metrics
        DetailSection("Performance Metrics") {
            DetailRow("Total Trades", "${performance.totalTrades}")
            DetailRow("Completed Trades", "${performance.completedTrades}")
            DetailRow("Winning Trades", "${performance.winningTrades}", isPositive = true)
            DetailRow("Losing Trades", "${performance.losingTrades}", isPositive = false)
            DetailRow("Avg Profit/Trade", FormatUtils.formatCurrency(performance.avgProfitPerTrade))
            DetailRow("Largest Win", FormatUtils.formatCurrency(performance.largestWin), isPositive = true)
            DetailRow("Largest Loss", FormatUtils.formatCurrency(performance.largestLoss), isPositive = false)
            DetailRow("Realized PnL", FormatUtils.formatCurrency(performance.totalRealizedPnl), performance.totalRealizedPnl >= 0)
            DetailRow("Unrealized PnL", FormatUtils.formatCurrency(performance.totalUnrealizedPnl), performance.totalUnrealizedPnl >= 0)
        }
        
        // Current Position
        if (performance.positionSide != null && performance.positionSize != null && performance.positionSize > 0) {
            DetailSection("Current Position") {
                DetailRow("Position Side", performance.positionSide)
                DetailRow("Position Size", "${String.format("%.4f", performance.positionSize)}")
                performance.entryPrice?.let {
                    DetailRow("Entry Price", FormatUtils.formatCurrency(it))
                }
                performance.currentPrice?.let {
                    DetailRow("Current Price", FormatUtils.formatCurrency(it))
                }
                DetailRow("Unrealized PnL", FormatUtils.formatCurrency(performance.totalUnrealizedPnl), performance.totalUnrealizedPnl >= 0)
            }
        }
        
        // Strategy Configuration
        DetailSection("Strategy Configuration") {
            DetailRow("Strategy Type", performance.strategyType)
            performance.accountId?.let {
                DetailRow("Account", it)
            }
            DetailRow("Leverage", "${performance.leverage}x")
            DetailRow("Risk per Trade", "${String.format("%.2f", performance.riskPerTrade * 100)}%")
            performance.fixedAmount?.let {
                DetailRow("Fixed Amount", FormatUtils.formatCurrency(it))
            }
        }
        
        // Strategy Parameters
        if (performance.params.isNotEmpty()) {
            DetailSection("Strategy Parameters") {
                val relevantParams = getRelevantParamsForStrategy(performance.strategyType, performance.params)
                relevantParams.forEach { (key, value) ->
                    DetailRow(
                        key.replace("_", " ").replaceFirstChar { it.uppercase() },
                        formatParamValueForDisplay(value)
                    )
                }
            }
        }
        
        // Timestamps
        DetailSection("Timestamps") {
            DetailRow("Created", FormatUtils.formatDateTime(performance.createdAt))
            performance.startedAt?.let {
                DetailRow("Last Started", FormatUtils.formatDateTime(it))
            }
            performance.stoppedAt?.let {
                DetailRow("Last Stopped", FormatUtils.formatDateTime(it))
            }
            performance.lastTradeAt?.let {
                DetailRow("Last Trade", FormatUtils.formatDateTime(it))
            }
            performance.lastSignal?.let {
                DetailRow("Last Signal", it)
            }
        }
        
        // Auto-Tuning Status
        DetailSection("Auto-Tuning") {
            DetailRow("Status", if (performance.autoTuningEnabled) "Enabled" else "Disabled")
        }
        
        // Health Status Section (for running strategies)
        if (performance.status == "running") {
            StrategyHealthDetailsSection(
                strategyId = performance.strategyId,
                health = strategyHealth,
                onLoadHealth = onLoadStrategyHealth
            )
        }
        
        // Risk Configuration Section
        StrategyRiskConfigSection(
            strategyId = performance.strategyId,
            strategyName = performance.strategyName,
            strategyRiskConfig = strategyRiskConfig,
            isLoadingRisk = isLoadingRisk,
            onLoadConfig = onLoadRiskConfig,
            onCreateConfig = onCreateRiskConfig,
            onUpdateConfig = onUpdateRiskConfig
        )
    }
}

fun getRelevantParamsForStrategy(strategyType: String, params: Map<String, Any>): Map<String, Any> {
    val emaScalpingParams = listOf(
        "ema_fast", "ema_slow", "take_profit_pct", "stop_loss_pct",
        "interval_seconds", "kline_interval", "enable_short",
        "min_ema_separation", "enable_htf_bias", "cooldown_candles",
        "trailing_stop_enabled", "trailing_stop_activation_pct", "sl_trigger_mode"
    )
    
    val rangeMeanReversionParams = listOf(
        "lookback_period", "buy_zone_pct", "sell_zone_pct",
        "ema_fast_period", "ema_slow_period", "max_ema_spread_pct",
        "max_atr_multiplier", "rsi_period", "rsi_oversold",
        "rsi_overbought", "tp_buffer_pct", "sl_buffer_pct", "kline_interval",
        "sl_trigger_mode"
    )
    
    val relevantKeys = when {
        strategyType == "scalping" || strategyType == "ema_crossover" || strategyType == "reverse_scalping" -> emaScalpingParams
        strategyType == "range_mean_reversion" -> rangeMeanReversionParams
        else -> params.keys.toList()
    }
    
    return params.filterKeys { it in relevantKeys }
}

fun formatParamValueForDisplay(value: Any?): String {
    return when (value) {
        is Boolean -> value.toString()
        is Double -> String.format(Locale.getDefault(), "%.4f", value)
        is Float -> String.format(Locale.getDefault(), "%.4f", value)
        is Number -> value.toString()
        null -> "N/A"
        else -> value.toString()
    }
}

@Composable
fun DetailSection(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f)
        )
    ) {
        Column(
            modifier = Modifier.padding(Spacing.Small),
            verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary
            )
            content()
        }
    }
}

@Composable
fun StrategyHealthIndicator(
    strategyId: String,
    health: StrategyHealthDto?,
    onLoadHealth: () -> Unit,
    loadWhenVisible: Boolean = true
) {
    var isLoading by remember(strategyId) { mutableStateOf(loadWhenVisible) }
    
    LaunchedEffect(strategyId, loadWhenVisible) {
        if (loadWhenVisible) {
            isLoading = true
            AppLogger.d("StrategyHealth", "Loading health for strategy: $strategyId")
            onLoadHealth()
        }
    }
    LaunchedEffect(health) {
        if (health != null) {
            isLoading = false
            AppLogger.d("StrategyHealth", "Health loaded for $strategyId: ${health.healthStatus}")
        }
    }
    LaunchedEffect(strategyId, loadWhenVisible) {
        if (!loadWhenVisible) return@LaunchedEffect
        delay(2000)
        if (health == null && isLoading) {
            isLoading = false
            AppLogger.d("StrategyHealth", "No health data for $strategyId after timeout")
        }
    }
    
    val healthStatus = health?.healthStatus
    
    val color = when {
        isLoading -> MaterialTheme.colorScheme.onSurfaceVariant
        healthStatus == "execution_stale" -> MaterialTheme.colorScheme.error
        healthStatus == "task_dead" -> MaterialTheme.colorScheme.error
        healthStatus == "no_execution_tracking" -> MaterialTheme.colorScheme.onSurfaceVariant
        healthStatus == "no_recent_orders" -> MaterialTheme.colorScheme.errorContainer
        healthStatus == "healthy" -> MaterialTheme.colorScheme.primary
        health == null && !loadWhenVisible -> MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
        else -> MaterialTheme.colorScheme.primary
    }
    
    // Simple icon-only health indicator - no border, no text, just colored icon
    AppLogger.d("StrategyHealth", "Rendering icon for $strategyId: isLoading=$isLoading, healthStatus=$healthStatus")
    
    Box(
        modifier = Modifier.size(24.dp),
        contentAlignment = Alignment.Center
    ) {
        if (isLoading) {
            CircularProgressIndicator(
                modifier = Modifier.size(20.dp),
                strokeWidth = 2.dp,
                color = color
            )
        } else {
            val vector = when (healthStatus) {
                "execution_stale" -> Icons.Default.Warning
                "task_dead" -> Icons.Default.Cancel
                "no_execution_tracking" -> Icons.Default.Help
                "no_recent_orders" -> Icons.Default.Warning
                "healthy" -> Icons.Default.CheckCircle
                else -> Icons.Default.CheckCircle
            }
            Icon(
                imageVector = if (health == null && !loadWhenVisible) Icons.Default.Remove else vector,
                contentDescription = when (healthStatus) {
                    "execution_stale" -> "Stale"
                    "task_dead" -> "Dead"
                    "no_execution_tracking" -> "No tracking"
                    "no_recent_orders" -> "No orders"
                    "healthy" -> "Healthy"
                    else -> "Health status"
                },
                tint = color,
                modifier = Modifier.size(20.dp)
            )
        }
    }
}

@Composable
fun StrategyHealthDetailsSection(
    strategyId: String,
    health: StrategyHealthDto?,
    onLoadHealth: () -> Unit
) {
    LaunchedEffect(strategyId) {
        onLoadHealth()
    }
    DetailSection("Execution Health Status") {
        if (health != null) {
            val statusText = when (health.healthStatus) {
                "healthy" -> "Healthy - Strategy is executing normally"
                "execution_stale" -> "Stale - Last execution was too long ago"
                "task_dead" -> "Dead - Execution task has crashed"
                "no_execution_tracking" -> "? No Tracking - Execution tracking not available"
                "no_recent_orders" -> "No Orders - Strategy running but not placing orders"
                else -> "? Unknown Status"
            }
            
            DetailRow("Status", statusText)
            
            health.issues?.takeIf { it.isNotEmpty() }?.let { issues ->
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                Text(
                    text = "Issues:",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.error
                )
                issues.forEach { issue ->
                    Text(
                        text = "- $issue",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(start = Spacing.Medium, top = Spacing.Tiny)
                    )
                }
            }
            
            health.executionStatus?.let { execStatus ->
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                execStatus["last_execution_age_seconds"]?.let { ageSeconds ->
                    val ageMinutes = (ageSeconds as? Number)?.toDouble()?.div(60) ?: 0.0
                    DetailRow("Last Execution", "${String.format("%.1f", ageMinutes)} minutes ago")
                }
                execStatus["execution_stale"]?.let { stale ->
                    if (stale == true) {
                        DetailRow("Execution Status", "Stale", isPositive = false)
                    }
                }
            }
            
            health.taskStatus?.let { taskStatus ->
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                taskStatus["task_running"]?.let { running ->
                    DetailRow("Task Running", if (running == true) "Yes" else "No", isPositive = running == true)
                }
                taskStatus["task_done"]?.let { done ->
                    if (done == true) {
                        DetailRow("Task Status", "Task has exited", isPositive = false)
                    }
                }
            }
        } else {
            DetailRow("Status", "Loading health status...")
        }
    }
}

@Composable
fun StrategyRiskConfigSection(
    strategyId: String,
    strategyName: String,
    strategyRiskConfig: com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto?,
    isLoadingRisk: Boolean,
    onLoadConfig: () -> Unit,
    onCreateConfig: (com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto) -> Unit,
    onUpdateConfig: (com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto) -> Unit
) {
    var showRiskConfigDialog by remember { mutableStateOf(false) }
    LaunchedEffect(strategyId) { onLoadConfig() }
    val configExists = strategyRiskConfig != null
    DetailSection("Strategy Level Risk Configuration") {
        if (isLoadingRisk) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center
            ) {
                CircularProgressIndicator(modifier = Modifier.size(24.dp))
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text(
                    text = "Loading risk configuration...",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else if (configExists) {
            strategyRiskConfig?.let { config ->
                DetailRow("Status", "Configured", isPositive = true)
                if (config.enabled == true) {
                    DetailRow("Enabled", "Yes", isPositive = true)
                }
                config.maxDailyLossUsdt?.let {
                    DetailRow("Max Daily Loss", FormatUtils.formatCurrency(it))
                }
                config.maxDailyLossPct?.let {
                    DetailRow("Max Daily Loss %", "${String.format("%.2f", it * 100)}%")
                }
                config.maxWeeklyLossUsdt?.let {
                    DetailRow("Max Weekly Loss", FormatUtils.formatCurrency(it))
                }
                config.maxWeeklyLossPct?.let {
                    DetailRow("Max Weekly Loss %", "${String.format("%.2f", it * 100)}%")
                }
                config.maxDrawdownPct?.let {
                    DetailRow("Max Drawdown", "${String.format("%.2f", it * 100)}%")
                }
            }
            Button(
                onClick = { showRiskConfigDialog = true },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            ) {
                Icon(Icons.Default.Edit, null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text("Edit Risk Config")
            }
        } else {
            DetailRow("Status", "Not Configured", isPositive = false)
            Text(
                text = "No custom risk configuration set. Using account-level limits.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(vertical = Spacing.Small)
            )
            Button(
                onClick = { showRiskConfigDialog = true },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.primary
                )
            ) {
                Icon(Icons.Default.Add, null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text("Configure Risk")
            }
        }
    }
    
    if (showRiskConfigDialog) {
        com.binancebot.mobile.presentation.screens.risk.StrategyRiskConfigDialogWithCallbacks(
            strategyId = strategyId,
            strategyName = strategyName,
            onDismiss = { showRiskConfigDialog = false },
            initialConfig = strategyRiskConfig,
            onCreate = onCreateConfig,
            onUpdate = onUpdateConfig
        )
    }
}

@Composable
fun StrategyRiskConfigSectionWithViewModel(
    strategyId: String,
    strategyName: String,
    viewModel: com.binancebot.mobile.presentation.viewmodel.RiskManagementViewModel
) {
    val strategyRiskConfigs by viewModel.strategyRiskConfigs.collectAsState()
    val loadingStrategyRiskId by viewModel.loadingStrategyRiskId.collectAsState()
    val config = strategyRiskConfigs[strategyId]
    val isLoadingRisk = loadingStrategyRiskId == strategyId
    StrategyRiskConfigSection(
        strategyId = strategyId,
        strategyName = strategyName,
        strategyRiskConfig = config,
        isLoadingRisk = isLoadingRisk,
        onLoadConfig = { viewModel.loadStrategyRiskConfig(strategyId) },
        onCreateConfig = { viewModel.createStrategyRiskConfig(it) },
        onUpdateConfig = { viewModel.updateStrategyRiskConfig(strategyId, it) }
    )
}

/**
 * Displays account-level risk configuration (read-only).
 * Used on Strategy Details to show the account limits that apply when no strategy-level config exists.
 */
@Composable
fun AccountRiskConfigSection(
    accountId: String,
    riskConfig: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?,
    isLoading: Boolean
) {
    DetailSection("Account Risk Configuration") {
        if (isLoading) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center
            ) {
                CircularProgressIndicator(modifier = Modifier.size(24.dp))
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text(
                    text = "Loading account risk configuration...",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else if (riskConfig != null) {
            DetailRow("Account", accountId)
            DetailRow("Status", "Configured", isPositive = true)
            riskConfig.maxPortfolioExposureUsdt?.let {
                DetailRow("Max Portfolio Exposure", FormatUtils.formatCurrency(it))
            }
            riskConfig.maxPortfolioExposurePct?.let {
                DetailRow("Max Portfolio Exposure %", "${String.format("%.2f", it)}%")
            }
            riskConfig.maxDailyLossUsdt?.let {
                DetailRow("Max Daily Loss", FormatUtils.formatCurrency(it))
            }
            riskConfig.maxDailyLossPct?.let {
                DetailRow("Max Daily Loss %", "${String.format("%.2f", if (it <= 1) it * 100 else it)}%")
            }
            riskConfig.maxWeeklyLossUsdt?.let {
                DetailRow("Max Weekly Loss", FormatUtils.formatCurrency(it))
            }
            riskConfig.maxWeeklyLossPct?.let {
                DetailRow("Max Weekly Loss %", "${String.format("%.2f", if (it <= 1) it * 100 else it)}%")
            }
            riskConfig.maxDrawdownPct?.let {
                DetailRow("Max Drawdown", "${String.format("%.2f", if (it <= 1) it * 100 else it)}%")
            }
            if (riskConfig.circuitBreakerEnabled) {
                DetailRow("Circuit Breaker", "Enabled", isPositive = true)
            }
        } else {
            DetailRow("Status", "Not Configured", isPositive = false)
            Text(
                text = "No risk configuration for this account. Strategy will use default behavior.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(vertical = Spacing.Small)
            )
        }
    }
}

@Composable
fun DetailRow(label: String, value: String, isPositive: Boolean? = null) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Medium,
            color = when {
                isPositive == true -> MaterialTheme.colorScheme.primary
                isPositive == false -> MaterialTheme.colorScheme.error
                else -> MaterialTheme.colorScheme.onSurface
            }
        )
    }
}
