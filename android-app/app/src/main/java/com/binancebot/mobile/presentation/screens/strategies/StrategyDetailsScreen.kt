package com.binancebot.mobile.presentation.screens.strategies

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.History
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.components.StatusBadge
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.StrategyDetailsViewModel
import com.binancebot.mobile.presentation.viewmodel.StrategyDetailsUiState
import com.binancebot.mobile.presentation.viewmodel.RiskManagementViewModel
import com.binancebot.mobile.presentation.viewmodel.StrategiesViewModel
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StrategyDetailsScreen(
    strategyId: String,
    navController: NavController,
    viewModel: StrategyDetailsViewModel = hiltViewModel(),
    riskManagementViewModel: RiskManagementViewModel = hiltViewModel(),
    strategiesViewModel: StrategiesViewModel = hiltViewModel()
) {
    val strategy by viewModel.strategy.collectAsState()
    val stats by viewModel.stats.collectAsState()
    val performance by viewModel.performance.collectAsState()
    val activity by viewModel.activity.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    val actionInProgress by viewModel.actionInProgress.collectAsState()
    
    LaunchedEffect(strategyId) {
        viewModel.loadStrategyDetails(strategyId)
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(strategy?.name ?: "Strategy Details") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.refresh(strategyId) }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                }
            )
        }
    ) { padding ->
        when (uiState) {
            is StrategyDetailsUiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
            is StrategyDetailsUiState.Error -> {
                ErrorHandler(
                    message = (uiState as StrategyDetailsUiState.Error).message,
                    onRetry = { viewModel.refresh(strategyId) },
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                )
            }
            else -> {
                strategy?.let { strat ->
                    // Load account-level risk config when strategy (and thus accountId) is available
                    LaunchedEffect(strat.accountId) {
                        riskManagementViewModel.loadRiskConfig(strat.accountId)
                    }
                    val accountRiskConfig by riskManagementViewModel.riskConfig.collectAsState()
                    val accountRiskForThisStrategy = accountRiskConfig?.takeIf { it.accountId == strat.accountId }
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding)
                            .verticalScroll(rememberScrollState())
                            .padding(Spacing.ScreenPadding),
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        // Header Card
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
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = strat.name,
                                            style = MaterialTheme.typography.headlineSmall,
                                            fontWeight = FontWeight.Bold
                                        )
                                        Text(
                                            text = "${strat.symbol} • ${strat.strategyType}",
                                            style = MaterialTheme.typography.bodyMedium,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                    StatusBadge(status = strat.status)
                                }
                                
                                HorizontalDivider()
                                
                                // Quick Actions
                                val isActionLoading = actionInProgress == strategyId
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                                ) {
                                    if (strat.isRunning) {
                                        Button(
                                            onClick = { viewModel.stopStrategy(strategyId) },
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
                                    } else {
                                        Button(
                                            onClick = { viewModel.startStrategy(strategyId) },
                                            modifier = Modifier.weight(1f),
                                            enabled = !isActionLoading
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
                                    }
                                }
                            }
                        }
                        
                        // Performance Metrics - use performance data (stats endpoint doesn't exist)
                        performance?.let { perf ->
                            MetricSection(
                                title = "Performance Metrics",
                                items = listOf(
                                    "Total Trades" to perf.totalTrades.toString(),
                                    "Completed Trades" to perf.completedTrades.toString(),
                                    "Winning Trades" to perf.winningTrades.toString(),
                                    "Losing Trades" to perf.losingTrades.toString(),
                                    "Win Rate" to "${String.format("%.2f", if (perf.winRate > 1.0) perf.winRate else perf.winRate * 100)}%",
                                    "Total PnL" to FormatUtils.formatCurrency(perf.totalPnl),
                                    "Realized PnL" to FormatUtils.formatCurrency(perf.totalRealizedPnl),
                                    "Unrealized PnL" to FormatUtils.formatCurrency(perf.totalUnrealizedPnl),
                                    "Avg Profit/Trade" to FormatUtils.formatCurrency(perf.avgProfitPerTrade),
                                    "Largest Win" to FormatUtils.formatCurrency(perf.largestWin),
                                    "Largest Loss" to FormatUtils.formatCurrency(perf.largestLoss)
                                )
                            )
                        } ?: stats?.let {
                            // Fallback to stats if performance is not available
                            MetricSection(
                                title = "Performance Metrics",
                                items = listOf(
                                    "Total Trades" to it.totalTrades.toString(),
                                    "Winning Trades" to "${it.winningTrades}",
                                    "Losing Trades" to "${it.losingTrades}",
                                    "Win Rate" to "${String.format("%.2f", it.winRate * 100)}%",
                                    "Total PnL" to FormatUtils.formatCurrency(it.totalPnl),
                                    "Realized PnL" to FormatUtils.formatCurrency(it.realizedPnl ?: 0.0),
                                    "Unrealized PnL" to FormatUtils.formatCurrency(it.unrealizedPnl ?: 0.0),
                                    "Avg Profit/Trade" to FormatUtils.formatCurrency(it.avgProfitPerTrade),
                                    "Largest Win" to FormatUtils.formatCurrency(it.largestWin ?: 0.0),
                                    "Largest Loss" to FormatUtils.formatCurrency(it.largestLoss ?: 0.0)
                                )
                            )
                        }
                        
                        // Trade History — navigates to same report trade history as in Reports
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    navController.navigate("report_strategy_trades/$strategyId")
                                },
                            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(Spacing.CardPadding),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                                ) {
                                    Icon(
                                        Icons.Outlined.History,
                                        contentDescription = null,
                                        tint = MaterialTheme.colorScheme.primary
                                    )
                                    Column {
                                        Text(
                                            text = "Trade History",
                                            style = MaterialTheme.typography.titleMedium,
                                            fontWeight = FontWeight.Bold
                                        )
                                        Text(
                                            text = "View full trade history for this strategy",
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                }
                                Icon(
                                    Icons.Default.ChevronRight,
                                    contentDescription = "Open"
                                )
                            }
                        }

                        // Current Position
                        PositionSection(strategy = strat)
                        
                        // Strategy Configuration
                        ConfigurationSection(strategy = strat)
                        
                        // Strategy Parameters (from performance data)
                        performance?.let { perf ->
                            StrategyParametersSection(performance = perf)
                        }
                        
                        // Timestamps (from performance data)
                        performance?.let { perf ->
                            TimestampsSection(performance = perf)
                        }
                        
                        // Auto-Tuning Status (from performance data)
                        performance?.let { perf ->
                            AutoTuningSection(performance = perf)
                        }
                        
                        // Execution Health (collapsible, for running strategies only)
                        if (strat.isRunning) {
                            var expandedExecutionHealth by remember { mutableStateOf(false) }
                            Card(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { expandedExecutionHealth = !expandedExecutionHealth },
                                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                            ) {
                                Column(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(Spacing.CardPadding)
                                ) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text(
                                            text = "Execution Health",
                                            style = MaterialTheme.typography.titleMedium,
                                            fontWeight = FontWeight.Bold
                                        )
                                        Icon(
                                            imageVector = if (expandedExecutionHealth) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                                            contentDescription = if (expandedExecutionHealth) "Collapse" else "Expand"
                                        )
                                    }
                                    AnimatedVisibility(
                                        visible = expandedExecutionHealth,
                                        enter = expandVertically(),
                                        exit = shrinkVertically()
                                    ) {
                                        Column(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .padding(top = Spacing.Small)
                                        ) {
                                            HorizontalDivider()
                                            StrategyHealthDetailsSection(
                                                strategyId = strategyId,
                                                strategiesViewModel = strategiesViewModel
                                            )
                                        }
                                    }
                                }
                            }
                        }
                        
                        // Account Risk Configuration (for this strategy's account)
                        com.binancebot.mobile.presentation.screens.strategies.AccountRiskConfigSection(
                            accountId = strat.accountId,
                            riskConfig = accountRiskForThisStrategy,
                            isLoading = false
                        )
                        
                        // Strategy Risk Configuration (strategy-level overrides; always show when strategy is loaded)
                        com.binancebot.mobile.presentation.screens.strategies.StrategyRiskConfigSection(
                            strategyId = strategyId,
                            strategyName = strat.name,
                            viewModel = riskManagementViewModel
                        )
                        
                        // Activity History
                        ActivityHistorySection(activity = activity)
                    }
                } ?: run {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding),
                        contentAlignment = Alignment.Center
                    ) {
                        Text("Strategy not found")
                    }
                }
            }
        }
    }
}

@Composable
fun MetricSection(
    title: String,
    items: List<Pair<String, String>>,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.CardPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            items.forEach { (label, value) ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
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
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }
    }
}

@Composable
fun PositionSection(strategy: com.binancebot.mobile.domain.model.Strategy) {
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
                text = "Current Position",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            
            if (strategy.hasPosition) {
                strategy.positionSize?.let { size ->
                    MetricRow("Position Size", "${String.format("%.4f", size)}")
                }
                strategy.entryPrice?.let { price ->
                    MetricRow("Entry Price", FormatUtils.formatCurrency(price))
                }
                strategy.currentPrice?.let { price ->
                    MetricRow("Current Price", FormatUtils.formatCurrency(price))
                }
                strategy.positionSide?.let { side ->
                    MetricRow("Position Side", side)
                }
                strategy.unrealizedPnL?.let { pnl ->
                    MetricRow(
                        "Unrealized PnL",
                        FormatUtils.formatCurrency(pnl),
                        isHighlight = true,
                        isPositive = pnl >= 0
                    )
                }
            } else {
                Text(
                    text = "No open position",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
fun ConfigurationSection(strategy: com.binancebot.mobile.domain.model.Strategy) {
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
                text = "Strategy Configuration",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            MetricRow("Strategy Type", strategy.strategyType)
            MetricRow("Leverage", "${strategy.leverage}x")
            strategy.riskPerTrade?.let {
                MetricRow("Risk Per Trade", "${String.format("%.2f", it * 100)}%")
            }
            MetricRow("Account ID", strategy.accountId)
            strategy.lastSignal?.let {
                MetricRow("Last Signal", it)
            }
        }
    }
}

@Composable
fun MetricRow(
    label: String,
    value: String,
    isHighlight: Boolean = false,
    isPositive: Boolean = false
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
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
            fontWeight = if (isHighlight) FontWeight.Bold else null,
            color = when {
                isHighlight && isPositive -> MaterialTheme.colorScheme.primary
                isHighlight && !isPositive -> MaterialTheme.colorScheme.error
                else -> MaterialTheme.colorScheme.onSurface
            }
        )
    }
}

@Composable
fun StrategyParametersSection(performance: StrategyPerformanceDto) {
    if (performance.params.isEmpty()) return
    
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
                text = "Strategy Parameters",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            
            // Filter parameters based on strategy type
            val relevantParams = getRelevantParams(performance.strategyType, performance.params)
            
            relevantParams.forEach { (key, value) ->
                MetricRow(
                    label = key.replace("_", " ").replaceFirstChar { it.uppercase() },
                    value = formatParamValue(value)
                )
            }
        }
    }
}

@Composable
fun TimestampsSection(performance: StrategyPerformanceDto) {
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
                text = "Timestamps",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            
            MetricRow("Created", FormatUtils.formatDateTime(performance.createdAt))
            performance.startedAt?.let {
                MetricRow("Last Started", FormatUtils.formatDateTime(it))
            }
            performance.stoppedAt?.let {
                MetricRow("Last Stopped", FormatUtils.formatDateTime(it))
            }
            performance.lastTradeAt?.let {
                MetricRow("Last Trade", FormatUtils.formatDateTime(it))
            }
            performance.lastSignal?.let {
                MetricRow("Last Signal", it)
            }
        }
    }
}

@Composable
fun AutoTuningSection(performance: StrategyPerformanceDto) {
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
                text = "Auto-Tuning",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            
            MetricRow(
                "Status",
                if (performance.autoTuningEnabled) "Enabled" else "Disabled",
                isHighlight = true,
                isPositive = performance.autoTuningEnabled
            )
        }
    }
}

@Composable
fun RiskConfigurationSection(
    strategyId: String,
    accountId: String?,
    strategyName: String?,
    riskManagementViewModel: RiskManagementViewModel
) {
    // Use the same StrategyRiskConfigSection from StrategiesScreen
    com.binancebot.mobile.presentation.screens.strategies.StrategyRiskConfigSection(
        strategyId = strategyId,
        strategyName = strategyName ?: strategyId,
        viewModel = riskManagementViewModel
    )
}

@Composable
fun ActivityHistorySection(
    activity: List<com.binancebot.mobile.data.remote.dto.StrategyActivityDto>
) {
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
                text = "Activity History",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            
            if (activity.isEmpty()) {
                Text(
                    text = "No activity history available",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            } else {
                activity.forEachIndexed { index, event ->
                    ActivityEventItem(event = event)
                    if (index < activity.size - 1) {
                        HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.ExtraSmall))
                    }
                }
            }
        }
    }
}

@Composable
fun ActivityEventItem(
    event: com.binancebot.mobile.data.remote.dto.StrategyActivityDto
) {
    val eventColor = when (event.eventLevel.uppercase()) {
        "ERROR", "CRITICAL" -> MaterialTheme.colorScheme.error
        "WARNING" -> MaterialTheme.colorScheme.errorContainer
        "INFO" -> MaterialTheme.colorScheme.primary
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    
    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(Spacing.ExtraSmall)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = event.eventType.replace("_", " ").replaceFirstChar { it.uppercase() },
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold,
                color = eventColor
            )
            Text(
                text = FormatUtils.formatDateTime(event.createdAt),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        Text(
            text = event.message,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

fun getRelevantParams(strategyType: String, params: Map<String, Any>): Map<String, Any> {
    // Define parameters for each strategy type
    val emaScalpingParams = listOf(
        "ema_fast", "ema_slow", "take_profit_pct", "stop_loss_pct",
        "interval_seconds", "kline_interval", "enable_short",
        "min_ema_separation", "enable_htf_bias", "cooldown_candles",
        "trailing_stop_enabled", "trailing_stop_activation_pct"
    )
    
    val rangeMeanReversionParams = listOf(
        "lookback_period", "buy_zone_pct", "sell_zone_pct",
        "ema_fast_period", "ema_slow_period", "max_ema_spread_pct",
        "max_atr_multiplier", "rsi_period", "rsi_oversold",
        "rsi_overbought", "tp_buffer_pct", "sl_buffer_pct", "kline_interval"
    )
    
    val relevantKeys = when {
        strategyType == "scalping" || strategyType == "ema_crossover" || strategyType == "reverse_scalping" -> emaScalpingParams
        strategyType == "range_mean_reversion" -> rangeMeanReversionParams
        else -> params.keys.toList() // Show all if unknown type
    }
    
    return params.filterKeys { it in relevantKeys }
}

fun formatParamValue(value: Any?): String {
    return when (value) {
        is Boolean -> value.toString()
        is Double -> String.format(Locale.getDefault(), "%.4f", value)
        is Float -> String.format(Locale.getDefault(), "%.4f", value)
        is Number -> value.toString()
        null -> "N/A"
        else -> value.toString()
    }
}


