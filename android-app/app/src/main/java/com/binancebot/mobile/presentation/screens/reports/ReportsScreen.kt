package com.binancebot.mobile.presentation.screens.reports

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.data.remote.dto.StrategyReportDto
import com.binancebot.mobile.data.remote.dto.TradeReportDto
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.components.SwipeRefreshBox
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.ExportUtils
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.ReportsUiState
import com.binancebot.mobile.presentation.viewmodel.ReportsViewModel
import com.binancebot.mobile.presentation.viewmodel.AccountViewModel

/**
 * Helper function to format win rate correctly.
 * Backend returns 0-100 (e.g., 65.5 for 65.5%), so we don't multiply by 100.
 */
internal fun formatWinRate(winRate: Double): String {
    // Backend already returns percentage (0-100), not decimal (0-1)
    // If value is > 1, it's already a percentage; if <= 1, convert
    val percentage = if (winRate > 1.0) winRate else winRate * 100
    return String.format("%.1f%%", percentage)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReportsScreen(
    navController: NavController,
    viewModel: ReportsViewModel = hiltViewModel(),
    accountViewModel: AccountViewModel = hiltViewModel()
) {
    val tradingReport by viewModel.tradingReport.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    val accounts by accountViewModel.accounts.collectAsState()
    val context = LocalContext.current
    
    // Filter state
    var showFilters by remember { mutableStateOf(false) }
    var selectedTimeFilter by remember { mutableStateOf<String?>(null) }
    var selectedStrategyId by remember { mutableStateOf<String?>(null) }
    var selectedAccountId by remember { mutableStateOf<String?>(null) }
    
    // Export dialog state
    var showExportDialog by remember { mutableStateOf(false) }
    
    // Expanded strategy cards
    var expandedStrategyIds by remember { mutableStateOf(setOf<String>()) }
    
    // Calculate date range from time filter
    val dateRange = remember(selectedTimeFilter) {
        selectedTimeFilter?.let { filter ->
            val dateFormat = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.getDefault())
            val endCalendar = java.util.Calendar.getInstance()
            endCalendar.set(java.util.Calendar.HOUR_OF_DAY, 23)
            endCalendar.set(java.util.Calendar.MINUTE, 59)
            endCalendar.set(java.util.Calendar.SECOND, 59)
            val endDate = dateFormat.format(endCalendar.time)
            
            val startCalendar = java.util.Calendar.getInstance()
            startCalendar.set(java.util.Calendar.HOUR_OF_DAY, 0)
            startCalendar.set(java.util.Calendar.MINUTE, 0)
            startCalendar.set(java.util.Calendar.SECOND, 0)
            
            when (filter) {
                "today" -> { /* Already set to start of today */ }
                "week" -> startCalendar.add(java.util.Calendar.DAY_OF_YEAR, -7)
                "month" -> startCalendar.add(java.util.Calendar.MONTH, -1)
                "year" -> startCalendar.add(java.util.Calendar.YEAR, -1)
            }
            
            val startDate = dateFormat.format(startCalendar.time)
            Pair(startDate, endDate)
        }
    }
    
    // Reload when filters change
    LaunchedEffect(selectedStrategyId, dateRange, selectedAccountId) {
        viewModel.loadTradingReport(
            strategyId = selectedStrategyId,
            dateFrom = dateRange?.first,
            dateTo = dateRange?.second,
            accountId = selectedAccountId
        )
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Trading Reports") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    val hasActiveFilters = selectedTimeFilter != null || selectedStrategyId != null || selectedAccountId != null
                    IconButton(onClick = { showFilters = !showFilters }) {
                        BadgedBox(
                            badge = {
                                if (hasActiveFilters) {
                                    Badge { Text("!") }
                                }
                            }
                        ) {
                            Icon(
                                Icons.Default.FilterList,
                                contentDescription = "Filter",
                                tint = if (hasActiveFilters) MaterialTheme.colorScheme.primary
                                       else MaterialTheme.colorScheme.onSurface
                            )
                        }
                    }
                    IconButton(onClick = { showExportDialog = true }) {
                        Icon(Icons.Default.FileDownload, contentDescription = "Export")
                    }
                    IconButton(onClick = { 
                        viewModel.loadTradingReport(
                            strategyId = selectedStrategyId,
                            dateFrom = dateRange?.first,
                            dateTo = dateRange?.second,
                            accountId = selectedAccountId
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
                            dateTo = dateRange?.second,
                            accountId = selectedAccountId
                        )
                    },
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                )
            }
            else -> {
                SwipeRefreshBox(
                    isRefreshing = uiState is ReportsUiState.Loading,
                    onRefresh = { 
                        viewModel.loadTradingReport(
                            strategyId = selectedStrategyId,
                            dateFrom = dateRange?.first,
                            dateTo = dateRange?.second,
                            accountId = selectedAccountId
                        )
                    }
                ) {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding),
                        contentPadding = PaddingValues(Spacing.ScreenPadding),
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        // Filters Section
                        item {
                            AnimatedVisibility(
                                visible = showFilters,
                                enter = expandVertically(),
                                exit = shrinkVertically()
                            ) {
                                FiltersSection(
                                    accounts = accounts,
                                    selectedAccountId = selectedAccountId,
                                    onAccountSelected = { selectedAccountId = it },
                                    selectedTimeFilter = selectedTimeFilter,
                                    onTimeFilterSelected = { selectedTimeFilter = it },
                                    selectedStrategyId = selectedStrategyId,
                                    onStrategyIdChanged = { selectedStrategyId = it },
                                    onClearFilters = {
                                        selectedTimeFilter = null
                                        selectedStrategyId = null
                                        selectedAccountId = null
                                    }
                                )
                            }
                        }
                        
                        tradingReport?.let { report ->
                            // Overall Summary Card with Gradient
                            item {
                                OverallSummaryCard(
                                    totalTrades = report.totalTrades,
                                    totalStrategies = report.totalStrategies,
                                    overallWinRate = report.overallWinRate,
                                    overallNetPnl = report.overallNetPnl,
                                    reportGeneratedAt = report.reportGeneratedAt,
                                    onShare = {
                                        val text = ExportUtils.formatReportAsText(report)
                                        ExportUtils.shareText(context, text, "Share Trading Report")
                                    }
                                )
                            }
                            
                            // Win Rate Chart
                            if (report.strategies.isNotEmpty()) {
                                item {
                                    val winRateData = report.strategies.map { strategyReport ->
                                        val displayName = strategyReport.strategyName.take(12) + 
                                            if (strategyReport.strategyName.length > 12) "..." else ""
                                        // Backend returns 0-100, use directly
                                        val rate = if (strategyReport.winRate > 1.0) strategyReport.winRate.toFloat() 
                                                   else (strategyReport.winRate * 100).toFloat()
                                        displayName to rate
                                    }
                                    
                                    com.binancebot.mobile.presentation.components.charts.WinRateChart(
                                        data = winRateData,
                                        title = "Win Rate by Strategy"
                                    )
                                }
                            }
                            
                            // Strategy Reports Header
                            if (report.strategies.isNotEmpty()) {
                                item {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text(
                                            text = "Strategy Performance (${report.strategies.size})",
                                            style = MaterialTheme.typography.titleMedium,
                                            fontWeight = FontWeight.Bold
                                        )
                                        TextButton(
                                            onClick = {
                                                expandedStrategyIds = if (expandedStrategyIds.size == report.strategies.size) {
                                                    emptySet()
                                                } else {
                                                    report.strategies.map { it.strategyId }.toSet()
                                                }
                                            }
                                        ) {
                                            Text(if (expandedStrategyIds.size == report.strategies.size) "Collapse All" else "Expand All")
                                        }
                                    }
                                }
                            }
                            
                            // Strategy Cards
                            items(report.strategies, key = { it.strategyId }) { strategyReport ->
                                StrategyReportCard(
                                    strategyReport = strategyReport,
                                    isExpanded = expandedStrategyIds.contains(strategyReport.strategyId),
                                    onToggleExpand = {
                                        expandedStrategyIds = if (expandedStrategyIds.contains(strategyReport.strategyId)) {
                                            expandedStrategyIds - strategyReport.strategyId
                                        } else {
                                            expandedStrategyIds + strategyReport.strategyId
                                        }
                                    },
                                    onViewFullTradeHistory = {
                                        viewModel.setSelectedStrategyReport(strategyReport)
                                        navController.navigate("report_strategy_trades/${strategyReport.strategyId}")
                                    }
                                )
                            }
                        } ?: item {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(200.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Icon(
                                        Icons.Default.Assessment,
                                        contentDescription = null,
                                        modifier = Modifier.size(48.dp),
                                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Spacer(modifier = Modifier.height(Spacing.Small))
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
        
        // Export Dialog
        if (showExportDialog && tradingReport != null) {
            ExportDialog(
                onDismiss = { showExportDialog = false },
                onExportCsv = {
                    tradingReport?.let { report ->
                        val uri = ExportUtils.exportReportToCsv(context, report)
                        uri?.let {
                            ExportUtils.shareFile(context, it, "text/csv", "Share Trading Report (CSV)")
                        }
                    }
                    showExportDialog = false
                },
                onExportJson = {
                    tradingReport?.let { report ->
                        val uri = ExportUtils.exportReportToJson(context, report)
                        uri?.let {
                            ExportUtils.shareFile(context, it, "application/json", "Share Trading Report (JSON)")
                        }
                    }
                    showExportDialog = false
                }
            )
        }
    }
}

// FiltersSection, OverallSummaryCard, MetricCard, StrategyReportCard, QuickStat, TradeRow, ExportDialog -> ReportsCards.kt (P1.3)

