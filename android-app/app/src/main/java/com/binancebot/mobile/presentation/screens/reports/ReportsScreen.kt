package com.binancebot.mobile.presentation.screens.reports

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
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
import com.binancebot.mobile.presentation.viewmodel.ReportsViewModel
import com.binancebot.mobile.presentation.viewmodel.ReportsUiState
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material.icons.filled.FilterList
import androidx.compose.material.icons.filled.Share

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReportsScreen(
    navController: NavController,
    viewModel: ReportsViewModel = hiltViewModel()
) {
    val tradingReport by viewModel.tradingReport.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
    // Filter state
    var showFilters by remember { mutableStateOf(false) }
    var selectedTimeFilter by remember { mutableStateOf<String?>(null) }
    var selectedStrategyId by remember { mutableStateOf<String?>(null) }
    
    // Calculate date range from time filter
    val dateRange = remember(selectedTimeFilter) {
        selectedTimeFilter?.let { filter ->
            val dateFormat = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.getDefault())
            val endCalendar = java.util.Calendar.getInstance()
            val endDate = dateFormat.format(endCalendar.time)
            
            val startDate = when (filter) {
                "today" -> {
                    endDate // Same day
                }
                "week" -> {
                    val startCalendar = java.util.Calendar.getInstance()
                    startCalendar.add(java.util.Calendar.DAY_OF_YEAR, -7)
                    dateFormat.format(startCalendar.time)
                }
                "month" -> {
                    val startCalendar = java.util.Calendar.getInstance()
                    startCalendar.add(java.util.Calendar.MONTH, -1)
                    dateFormat.format(startCalendar.time)
                }
                "year" -> {
                    val startCalendar = java.util.Calendar.getInstance()
                    startCalendar.add(java.util.Calendar.YEAR, -1)
                    dateFormat.format(startCalendar.time)
                }
                else -> null
            }
            if (startDate != null) Pair(startDate, endDate) else null
        }
    }
    
    // Reload when filters change
    LaunchedEffect(selectedStrategyId, dateRange) {
        viewModel.loadTradingReport(
            strategyId = selectedStrategyId,
            dateFrom = dateRange?.first,
            dateTo = dateRange?.second
        )
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Trading Reports") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { showFilters = !showFilters }) {
                        Icon(
                            Icons.Default.FilterList,
                            contentDescription = "Filter",
                            tint = if (selectedTimeFilter != null || selectedStrategyId != null) {
                                MaterialTheme.colorScheme.primary
                            } else {
                                MaterialTheme.colorScheme.onSurface
                            }
                        )
                    }
                    IconButton(onClick = { 
                        viewModel.loadTradingReport(
                            strategyId = selectedStrategyId,
                            dateFrom = dateRange?.first,
                            dateTo = dateRange?.second
                        )
                    }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                }
            )
        }
    ) { padding ->
        when (uiState) {
            is ReportsUiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
            is ReportsUiState.Error -> {
                ErrorHandler(
                    message = (uiState as ReportsUiState.Error).message,
                    onRetry = { 
                        viewModel.loadTradingReport(
                            strategyId = selectedStrategyId,
                            dateFrom = dateRange?.first,
                            dateTo = dateRange?.second
                        )
                    },
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                )
            }
            else -> {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                ) {
                    // Time Filter Chips
                    if (showFilters) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = Spacing.ScreenPadding, vertical = Spacing.Small),
                            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                        ) {
                            FilterChip(
                                selected = selectedTimeFilter == null,
                                onClick = { selectedTimeFilter = null },
                                label = { Text("All Time") }
                            )
                            FilterChip(
                                selected = selectedTimeFilter == "today",
                                onClick = { selectedTimeFilter = if (selectedTimeFilter == "today") null else "today" },
                                label = { Text("Today") }
                            )
                            FilterChip(
                                selected = selectedTimeFilter == "week",
                                onClick = { selectedTimeFilter = if (selectedTimeFilter == "week") null else "week" },
                                label = { Text("This Week") }
                            )
                            FilterChip(
                                selected = selectedTimeFilter == "month",
                                onClick = { selectedTimeFilter = if (selectedTimeFilter == "month") null else "month" },
                                label = { Text("This Month") }
                            )
                            FilterChip(
                                selected = selectedTimeFilter == "year",
                                onClick = { selectedTimeFilter = if (selectedTimeFilter == "year") null else "year" },
                                label = { Text("This Year") }
                            )
                        }
                        Spacer(modifier = Modifier.height(Spacing.Small))
                    }
                    
                    Column(
                        modifier = Modifier
                            .weight(1f)
                            .verticalScroll(rememberScrollState())
                            .padding(Spacing.ScreenPadding),
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        tradingReport?.let { report ->
                            // Overall Summary
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
                                        Text(
                                            text = "Trading Report Summary",
                                            style = MaterialTheme.typography.titleLarge,
                                            fontWeight = FontWeight.Bold
                                        )
                                        Row(
                                            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                                        ) {
                                            IconButton(
                                            onClick = { 
                                                // Export functionality
                                                // TODO: Implement CSV export
                                                // This would require:
                                                // 1. Convert report data to CSV format
                                                // 2. Use Android FileProvider to save file
                                                // 3. Share via Intent
                                            },
                                            modifier = Modifier.size(40.dp)
                                        ) {
                                            Icon(
                                                Icons.Default.FileDownload,
                                                contentDescription = "Export",
                                                modifier = Modifier.size(20.dp)
                                            )
                                        }
                                        IconButton(
                                            onClick = { 
                                                // Share functionality
                                                // TODO: Implement share
                                                // This would require:
                                                // 1. Convert report to shareable format (text/JSON)
                                                // 2. Use Android ShareSheet
                                            },
                                            modifier = Modifier.size(40.dp)
                                        ) {
                                            Icon(
                                                Icons.Default.Share,
                                                contentDescription = "Share",
                                                modifier = Modifier.size(20.dp)
                                            )
                                        }
                                    }
                                    }
                                    Divider()
                                    
                                    // Metrics Grid (2x2)
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                                    ) {
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(
                                                text = "Total Trades",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                            Text(
                                                text = "${report.totalTrades ?: 0}",
                                                style = MaterialTheme.typography.headlineMedium,
                                                fontWeight = FontWeight.Bold
                                            )
                                        }
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(
                                                text = "Win Rate",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                            Text(
                                                text = "${String.format("%.2f", (report.overallWinRate ?: 0.0) * 100)}%",
                                                style = MaterialTheme.typography.headlineMedium,
                                                fontWeight = FontWeight.Bold
                                            )
                                        }
                                    }
                                    
                                    Spacer(modifier = Modifier.height(Spacing.Small))
                                    
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                                    ) {
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(
                                                text = "Total Strategies",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                            Text(
                                                text = "${report.totalStrategies ?: 0}",
                                                style = MaterialTheme.typography.headlineMedium,
                                                fontWeight = FontWeight.Bold
                                            )
                                        }
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(
                                                text = "Total PnL",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                            Text(
                                                text = FormatUtils.formatCurrency(report.overallNetPnl ?: 0.0),
                                                style = MaterialTheme.typography.headlineMedium,
                                                fontWeight = FontWeight.Bold,
                                                color = if ((report.overallNetPnl ?: 0.0) >= 0) {
                                                    MaterialTheme.colorScheme.primary
                                                } else {
                                                    MaterialTheme.colorScheme.error
                                                }
                                            )
                                        }
                                    }
                                    
                                    // Report Generated At
                                    report.reportGeneratedAt?.let {
                                        Spacer(modifier = Modifier.height(Spacing.Small))
                                        Text(
                                            text = "Generated: $it",
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                }
                            }
                            
                            // Win Rate Chart for Strategies
                            if (report.strategies != null && report.strategies.isNotEmpty()) {
                                val winRateData = report.strategies.map { strategyReport ->
                                    (strategyReport.strategyName ?: "Unknown") to 
                                        ((strategyReport.winRate ?: 0.0) * 100).toFloat()
                                }
                                
                                com.binancebot.mobile.presentation.components.charts.WinRateChart(
                                    data = winRateData,
                                    title = "Win Rate by Strategy"
                                )
                            }
                            
                            // Strategy Reports
                            if (report.strategies != null && report.strategies.isNotEmpty()) {
                                Text(
                                    text = "Strategy Performance",
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.Bold
                                )
                                
                                report.strategies.forEach { strategyReport ->
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
                                                text = strategyReport.strategyName ?: "Unknown Strategy",
                                                style = MaterialTheme.typography.titleMedium,
                                                fontWeight = FontWeight.Bold
                                            )
                                            Divider()
                                            
                                            MetricRow("Total Trades", "${strategyReport.totalTrades ?: 0}")
                                            MetricRow("Win Rate", "${String.format("%.2f", (strategyReport.winRate ?: 0.0) * 100)}%")
                                            MetricRow("Total PnL", FormatUtils.formatCurrency(strategyReport.netPnl ?: 0.0))
                                            // Calculate profit factor if we have profit and loss data
                                            val profitFactor = if (strategyReport.totalLossUsd != 0.0) {
                                                strategyReport.totalProfitUsd / strategyReport.totalLossUsd
                                            } else null
                                            profitFactor?.let {
                                                MetricRow("Profit Factor", String.format("%.2f", it))
                                            }
                                        }
                                    }
                                }
                            }
                        } ?: run {
                            Text(
                                text = "No trading report data available",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun MetricRow(
    label: String,
    value: String,
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
            fontWeight = FontWeight.Bold
        )
    }
}
