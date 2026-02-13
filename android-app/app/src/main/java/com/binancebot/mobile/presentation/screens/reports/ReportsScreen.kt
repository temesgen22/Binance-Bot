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
private fun formatWinRate(winRate: Double): String {
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FiltersSection(
    accounts: List<com.binancebot.mobile.domain.model.Account>,
    selectedAccountId: String?,
    onAccountSelected: (String?) -> Unit,
    selectedTimeFilter: String?,
    onTimeFilterSelected: (String?) -> Unit,
    selectedStrategyId: String?,
    onStrategyIdChanged: (String?) -> Unit,
    onClearFilters: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
        )
    ) {
        Column(
            modifier = Modifier.padding(Spacing.Medium),
            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            // Time Filter Chips
            Text(
                text = "Time Period",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            LazyRow(
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                val timeFilters = listOf(
                    null to "All Time",
                    "today" to "Today",
                    "week" to "This Week",
                    "month" to "This Month",
                    "year" to "This Year"
                )
                items(timeFilters) { (value, label) ->
                    FilterChip(
                        selected = selectedTimeFilter == value,
                        onClick = { onTimeFilterSelected(value) },
                        label = { Text(label) }
                    )
                }
            }
            
            // Account Filter
            if (accounts.isNotEmpty()) {
                Text(
                    text = "Account",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                var accountExpanded by remember { mutableStateOf(false) }
                ExposedDropdownMenuBox(
                    expanded = accountExpanded,
                    onExpandedChange = { accountExpanded = !accountExpanded }
                ) {
                    OutlinedTextField(
                        value = accounts.find { it.accountId == selectedAccountId }?.name ?: "All Accounts",
                        onValueChange = {},
                        readOnly = true,
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = accountExpanded) },
                        colors = OutlinedTextFieldDefaults.colors()
                    )
                    ExposedDropdownMenu(
                        expanded = accountExpanded,
                        onDismissRequest = { accountExpanded = false }
                    ) {
                        DropdownMenuItem(
                            text = { Text("All Accounts") },
                            onClick = {
                                onAccountSelected(null)
                                accountExpanded = false
                            }
                        )
                        accounts.forEach { account ->
                            DropdownMenuItem(
                                text = { 
                                    Text("${account.name ?: account.accountId}${if (account.testnet) " [TESTNET]" else ""}") 
                                },
                                onClick = {
                                    onAccountSelected(account.accountId)
                                    accountExpanded = false
                                }
                            )
                        }
                    }
                }
            }
            
            // Strategy Filter
            Text(
                text = "Strategy ID",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            OutlinedTextField(
                value = selectedStrategyId ?: "",
                onValueChange = { onStrategyIdChanged(if (it.isBlank()) null else it) },
                placeholder = { Text("Enter strategy ID") },
                modifier = Modifier.fillMaxWidth(),
                trailingIcon = if (selectedStrategyId != null) {
                    {
                        IconButton(onClick = { onStrategyIdChanged(null) }) {
                            Icon(Icons.Default.Clear, contentDescription = "Clear")
                        }
                    }
                } else null,
                singleLine = true
            )
            
            // Clear All Button
            val hasFilters = selectedTimeFilter != null || selectedStrategyId != null || selectedAccountId != null
            if (hasFilters) {
                TextButton(
                    onClick = onClearFilters,
                    modifier = Modifier.align(Alignment.End)
                ) {
                    Icon(Icons.Default.Clear, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Clear All Filters")
                }
            }
        }
    }
}

@Composable
private fun OverallSummaryCard(
    totalTrades: Int,
    totalStrategies: Int,
    overallWinRate: Double,
    overallNetPnl: Double,
    reportGeneratedAt: String,
    onShare: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    Brush.horizontalGradient(
                        colors = listOf(
                            MaterialTheme.colorScheme.primaryContainer,
                            MaterialTheme.colorScheme.secondaryContainer
                        )
                    )
                )
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
                    Text(
                        text = "Trading Report Summary",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                    IconButton(onClick = onShare) {
                        Icon(Icons.Default.Share, contentDescription = "Share")
                    }
                }
                
                // Metrics Grid (2x2)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    MetricCard(
                        label = "Total Trades",
                        value = "$totalTrades",
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        label = "Win Rate",
                        value = formatWinRate(overallWinRate),
                        valueColor = if (overallWinRate >= 50) MaterialTheme.colorScheme.primary 
                                     else MaterialTheme.colorScheme.error,
                        modifier = Modifier.weight(1f)
                    )
                }
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    MetricCard(
                        label = "Strategies",
                        value = "$totalStrategies",
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        label = "Net PnL",
                        value = FormatUtils.formatCurrency(overallNetPnl),
                        valueColor = if (overallNetPnl >= 0) MaterialTheme.colorScheme.primary 
                                     else MaterialTheme.colorScheme.error,
                        modifier = Modifier.weight(1f)
                    )
                }
                
                Text(
                    text = "Generated: $reportGeneratedAt",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun MetricCard(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    valueColor: Color = MaterialTheme.colorScheme.onSurface
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.8f)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Small),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                text = value,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = valueColor
            )
        }
    }
}

@Composable
private fun StrategyReportCard(
    strategyReport: StrategyReportDto,
    isExpanded: Boolean,
    onToggleExpand: () -> Unit,
    onViewFullTradeHistory: () -> Unit = {}
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onToggleExpand() },
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.CardPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = strategyReport.strategyName,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Text(
                        text = "${strategyReport.symbol} • ${strategyReport.strategyType ?: "Unknown"}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                
                // PnL Badge
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = if (strategyReport.netPnl >= 0) 
                        MaterialTheme.colorScheme.primaryContainer 
                    else 
                        MaterialTheme.colorScheme.errorContainer
                ) {
                    Text(
                        text = FormatUtils.formatCurrency(strategyReport.netPnl),
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (strategyReport.netPnl >= 0) 
                            MaterialTheme.colorScheme.onPrimaryContainer 
                        else 
                            MaterialTheme.colorScheme.onErrorContainer
                    )
                }
                
                Icon(
                    if (isExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                    contentDescription = if (isExpanded) "Collapse" else "Expand"
                )
            }
            
            // Quick Stats Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                QuickStat(
                    label = "Trades",
                    value = "${strategyReport.totalTrades}"
                )
                QuickStat(
                    label = "Win Rate",
                    value = formatWinRate(strategyReport.winRate),
                    valueColor = if (strategyReport.winRate >= 50) MaterialTheme.colorScheme.primary 
                                 else MaterialTheme.colorScheme.error
                )
                QuickStat(
                    label = "W/L",
                    value = "${strategyReport.wins}/${strategyReport.losses}",
                    valueColor = if (strategyReport.wins >= strategyReport.losses) 
                        MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                )
            }
            
            // Expanded Details
            AnimatedVisibility(visible = isExpanded) {
                Column(
                    modifier = Modifier.padding(top = Spacing.Small),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    HorizontalDivider()
                    
                    // Detailed Metrics
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column {
                            Text("Profit", style = MaterialTheme.typography.labelSmall, 
                                 color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(
                                FormatUtils.formatCurrency(strategyReport.totalProfitUsd),
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary
                            )
                        }
                        Column {
                            Text("Loss", style = MaterialTheme.typography.labelSmall,
                                 color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(
                                FormatUtils.formatCurrency(strategyReport.totalLossUsd),
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.error
                            )
                        }
                        Column {
                            Text("Profit Factor", style = MaterialTheme.typography.labelSmall,
                                 color = MaterialTheme.colorScheme.onSurfaceVariant)
                            val profitFactor = if (strategyReport.totalLossUsd != 0.0) {
                                strategyReport.totalProfitUsd / kotlin.math.abs(strategyReport.totalLossUsd)
                            } else if (strategyReport.totalProfitUsd > 0) Double.POSITIVE_INFINITY else 0.0
                            Text(
                                if (profitFactor.isInfinite()) "∞" else String.format("%.2f", profitFactor),
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                    
                    // Fees
                    if (strategyReport.totalFee > 0 || strategyReport.totalFundingFee != 0.0) {
                        HorizontalDivider()
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Column {
                                Text("Trading Fees", style = MaterialTheme.typography.labelSmall,
                                     color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(
                                    FormatUtils.formatCurrency(strategyReport.totalFee),
                                    style = MaterialTheme.typography.bodyMedium
                                )
                            }
                            Column {
                                Text("Funding Fees", style = MaterialTheme.typography.labelSmall,
                                     color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(
                                    FormatUtils.formatCurrency(strategyReport.totalFundingFee),
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = if (strategyReport.totalFundingFee >= 0) 
                                        MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                                )
                            }
                        }
                    }
                    
                    // Trade History (if available)
                    if (strategyReport.trades.isNotEmpty()) {
                        HorizontalDivider()
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "Recent Trades (${strategyReport.trades.size})",
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold
                            )
                            TextButton(onClick = onViewFullTradeHistory) {
                                Text("View full table")
                                Spacer(modifier = Modifier.width(4.dp))
                                Icon(
                                    Icons.Default.OpenInNew,
                                    contentDescription = null,
                                    modifier = Modifier.size(18.dp)
                                )
                            }
                        }
                        strategyReport.trades.take(5).forEach { trade ->
                            TradeRow(trade = trade)
                        }
                        if (strategyReport.trades.size > 5) {
                            Text(
                                text = "... and ${strategyReport.trades.size - 5} more trades",
                                style = MaterialTheme.typography.bodySmall,
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
private fun QuickStat(
    label: String,
    value: String,
    valueColor: Color = MaterialTheme.colorScheme.onSurface
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Bold,
            color = valueColor
        )
    }
}

@Composable
private fun TradeRow(trade: TradeReportDto) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Surface(
                shape = RoundedCornerShape(4.dp),
                color = if (trade.side == "LONG") MaterialTheme.colorScheme.primaryContainer 
                        else MaterialTheme.colorScheme.errorContainer
            ) {
                Text(
                    text = trade.side,
                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold
                )
            }
            Column {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = trade.exitReason ?: "Open",
                        style = MaterialTheme.typography.bodySmall
                    )
                    if (trade.trailingStopHistory.isNotEmpty()) {
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = MaterialTheme.colorScheme.tertiaryContainer
                        ) {
                            Text(
                                text = "Trail (${trade.trailingStopHistory.size})",
                                modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onTertiaryContainer
                            )
                        }
                    }
                }
                Text(
                    text = trade.exitTime?.take(10) ?: trade.entryTime?.take(10) ?: "",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
        Text(
            text = FormatUtils.formatCurrency(trade.pnlUsd),
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Bold,
            color = if (trade.pnlUsd >= 0) MaterialTheme.colorScheme.primary 
                    else MaterialTheme.colorScheme.error
        )
    }
}

@Composable
private fun ExportDialog(
    onDismiss: () -> Unit,
    onExportCsv: () -> Unit,
    onExportJson: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        icon = { Icon(Icons.Default.FileDownload, contentDescription = null) },
        title = { Text("Export Report") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.Small)) {
                Text("Choose export format:")
                
                OutlinedCard(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onExportCsv() }
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(Spacing.Medium),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.TableChart, contentDescription = null)
                        Spacer(modifier = Modifier.width(Spacing.Small))
                        Column {
                            Text("CSV Format", fontWeight = FontWeight.Bold)
                            Text(
                                "Spreadsheet compatible",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
                
                OutlinedCard(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onExportJson() }
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(Spacing.Medium),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.Code, contentDescription = null)
                        Spacer(modifier = Modifier.width(Spacing.Small))
                        Column {
                            Text("JSON Format", fontWeight = FontWeight.Bold)
                            Text(
                                "Full data export",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {},
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}
