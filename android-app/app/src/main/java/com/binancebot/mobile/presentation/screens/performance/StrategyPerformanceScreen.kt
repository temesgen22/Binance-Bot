package com.binancebot.mobile.presentation.screens.performance

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
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
import com.binancebot.mobile.presentation.viewmodel.StrategyPerformanceViewModel
import com.binancebot.mobile.presentation.viewmodel.StrategyPerformanceUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StrategyPerformanceScreen(
    navController: NavController,
    viewModel: StrategyPerformanceViewModel = hiltViewModel()
) {
    val performanceList by viewModel.performanceList.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
    // Filter and sort state
    var showFilters by remember { mutableStateOf(false) }
    var sortBy by remember { mutableStateOf("total_pnl") }
    var selectedStrategies by remember { mutableStateOf<Set<String>>(emptySet()) }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Strategy Performance") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    if (selectedStrategies.size >= 2) {
                        IconButton(onClick = { 
                            navController.navigate("strategy_comparison/${selectedStrategies.joinToString(",")}")
                        }) {
                            Icon(Icons.Default.CompareArrows, contentDescription = "Compare")
                        }
                    }
                    IconButton(onClick = { showFilters = !showFilters }) {
                        Icon(
                            Icons.Default.FilterList,
                            contentDescription = "Filter",
                            tint = if (showFilters) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface
                        )
                    }
                    IconButton(onClick = { viewModel.loadPerformance(rankBy = sortBy) }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                }
            )
        }
    ) { padding ->
        when (uiState) {
            is StrategyPerformanceUiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
            is StrategyPerformanceUiState.Error -> {
                ErrorHandler(
                    message = (uiState as StrategyPerformanceUiState.Error).message,
                    onRetry = { viewModel.loadPerformance(rankBy = sortBy) },
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
                    // Sort Options
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = Spacing.ScreenPadding, vertical = Spacing.Small),
                        horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                    ) {
                        var expandedSort by remember { mutableStateOf(false) }
                        val sortOptions = mapOf(
                            "total_pnl" to "Total PnL",
                            "win_rate" to "Win Rate",
                            "total_trades" to "Total Trades",
                            "profit_factor" to "Profit Factor"
                        )
                        
                        ExposedDropdownMenuBox(
                            expanded = expandedSort,
                            onExpandedChange = { expandedSort = !expandedSort }
                        ) {
                            OutlinedTextField(
                                value = sortOptions[sortBy] ?: "Total PnL",
                                onValueChange = {},
                                readOnly = true,
                                label = { Text("Sort By") },
                                modifier = Modifier
                                    .weight(1f)
                                    .menuAnchor(),
                                trailingIcon = {
                                    ExposedDropdownMenuDefaults.TrailingIcon(expanded = expandedSort)
                                }
                            )
                            ExposedDropdownMenu(
                                expanded = expandedSort,
                                onDismissRequest = { expandedSort = false }
                            ) {
                                sortOptions.forEach { (key, label) ->
                                    DropdownMenuItem(
                                        text = { Text(label) },
                                        onClick = {
                                            sortBy = key
                                            expandedSort = false
                                            viewModel.loadPerformance(rankBy = sortBy)
                                        }
                                    )
                                }
                            }
                        }
                    }
                    
                    // Performance List
                    performanceList?.let { list ->
                        if (list.strategies.isEmpty()) {
                            Box(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .weight(1f),
                                contentAlignment = Alignment.Center
                            ) {
                                Column(
                                    horizontalAlignment = Alignment.CenterHorizontally
                                ) {
                                    Text(
                                        text = "No strategies found",
                                        style = MaterialTheme.typography.titleMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        } else {
                            LazyColumn(
                                modifier = Modifier.weight(1f),
                                contentPadding = androidx.compose.foundation.layout.PaddingValues(Spacing.ScreenPadding),
                                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                            ) {
                                items(
                                    items = list.strategies,
                                    key = { it.strategyId }
                                ) { performance ->
                                    PerformanceRankingCard(
                                        performance = performance,
                                        rank = performance.rank ?: 0,
                                        isSelected = selectedStrategies.contains(performance.strategyId),
                                        onSelect = {
                                            selectedStrategies = if (selectedStrategies.contains(performance.strategyId)) {
                                                selectedStrategies - performance.strategyId
                                            } else {
                                                selectedStrategies + performance.strategyId
                                            }
                                        },
                                        onDetails = {
                                            navController.navigate("strategy_details/${performance.strategyId}")
                                        }
                                    )
                                }
                            }
                        }
                    } ?: run {
                        Box(
                            modifier = Modifier
                                .fillMaxSize()
                                .weight(1f),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = "No performance data available",
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
fun PerformanceRankingCard(
    performance: com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto,
    rank: Int,
    isSelected: Boolean,
    onSelect: () -> Unit,
    onDetails: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onDetails),
        elevation = CardDefaults.cardElevation(
            defaultElevation = if (isSelected) 4.dp else 2.dp
        ),
        colors = CardDefaults.cardColors(
            containerColor = if (isSelected) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.surface
            }
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Medium),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Rank Badge
            Surface(
                shape = MaterialTheme.shapes.medium,
                color = when (rank) {
                    1 -> MaterialTheme.colorScheme.primary
                    2 -> MaterialTheme.colorScheme.secondary
                    3 -> MaterialTheme.colorScheme.tertiary
                    else -> MaterialTheme.colorScheme.surfaceVariant
                }
            ) {
                Text(
                    text = "#$rank",
                    modifier = androidx.compose.ui.Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = when (rank) {
                        1, 2, 3 -> MaterialTheme.colorScheme.onPrimary
                        else -> MaterialTheme.colorScheme.onSurfaceVariant
                    }
                )
            }
            
            // Strategy Info
            Column(
                modifier = Modifier.weight(1f)
            ) {
                Text(
                    text = performance.strategyName,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "${performance.symbol} • ${performance.strategyType}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(modifier = Modifier.height(Spacing.Tiny))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    StatusBadge(status = performance.status)
                    Text(
                        text = "Win: ${String.format("%.1f%%", performance.winRate * 100)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            
            // Performance Metrics
            Column(
                horizontalAlignment = Alignment.End
            ) {
                Text(
                    text = FormatUtils.formatCurrency(performance.totalPnl),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = if (performance.totalPnl >= 0) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.error
                    }
                )
                Text(
                    text = "${performance.totalTrades} trades",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            
            // Selection Checkbox
            Checkbox(
                checked = isSelected,
                onCheckedChange = { onSelect() }
            )
        }
    }
}
