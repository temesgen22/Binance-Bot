package com.binancebot.mobile.presentation.screens.strategies

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
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
import com.binancebot.mobile.presentation.components.StatusBadge
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.StrategyDetailsViewModel
import com.binancebot.mobile.presentation.viewmodel.StrategyDetailsUiState
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StrategyDetailsScreen(
    strategyId: String,
    navController: NavController,
    viewModel: StrategyDetailsViewModel = hiltViewModel()
) {
    val strategy by viewModel.strategy.collectAsState()
    val stats by viewModel.stats.collectAsState()
    val performance by viewModel.performance.collectAsState()
    val activity by viewModel.activity.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
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
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                                ) {
                                    if (strat.isRunning) {
                                        Button(
                                            onClick = { viewModel.stopStrategy(strategyId) },
                                            modifier = Modifier.weight(1f),
                                            colors = ButtonDefaults.buttonColors(
                                                containerColor = MaterialTheme.colorScheme.error
                                            )
                                        ) {
                                            Icon(Icons.Default.Stop, null, modifier = Modifier.size(18.dp))
                                            Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                                            Text("Stop")
                                        }
                                    } else {
                                        Button(
                                            onClick = { viewModel.startStrategy(strategyId) },
                                            modifier = Modifier.weight(1f)
                                        ) {
                                            Icon(Icons.Default.PlayArrow, null, modifier = Modifier.size(18.dp))
                                            Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                                            Text("Start")
                                        }
                                    }
                                }
                            }
                        }
                        
                        // Performance Metrics
                        stats?.let {
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
                        
                        // Risk Configuration (from performance data if available)
                        performance?.let { perf ->
                            RiskConfigurationSection(
                                strategyId = strategyId,
                                accountId = perf.accountId
                            )
                        }
                        
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
    accountId: String?
) {
    // Parameters kept for potential future API integration
    // Note: This section can be enhanced to fetch risk status from API
    // For now, it shows a placeholder that can be expanded when API is integrated
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
                text = "Risk Configuration",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            
            Text(
                text = "Risk configuration is managed at the account level. " +
                        "To view or edit risk settings, go to Risk Management screen.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            
            // Placeholder for future enhancement:
            // This section can be enhanced to fetch and display:
            // - Strategy-specific risk limits (if configured)
            // - Current risk status (can_trade, blocked_reasons)
            // - Risk checks (portfolio_exposure, daily_loss, weekly_loss, circuit_breaker)
            // - Risk metrics (current values vs limits)
            // 
            // API endpoint: GET /api/risk/status/strategy/{strategy_id}
            // This would require:
            // 1. Adding endpoint to BinanceBotApi
            // 2. Adding DTO for StrategyRiskStatusResponse
            // 3. Adding method to RiskManagementRepository
            // 4. Fetching in StrategyDetailsViewModel
            // 5. Displaying risk status and checks here
        }
    }
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


