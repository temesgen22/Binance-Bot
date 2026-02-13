package com.binancebot.mobile.presentation.screens.reports

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.data.remote.dto.StrategyReportDto
import com.binancebot.mobile.data.remote.dto.TradeReportDto
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.ReportsViewModel

private fun formatWinRate(winRate: Double): String {
    val percentage = if (winRate > 1.0) winRate else winRate * 100
    return String.format("%.1f%%", percentage)
}

/** Cell width for table columns so all parameters are visible when scrolling. */
private val ColWidth = 110.dp
private val ColWidthWide = 140.dp
private val ColWidthNarrow = 72.dp

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StrategyReportDetailScreen(
    strategyId: String,
    navController: NavController,
    viewModel: ReportsViewModel = hiltViewModel()
) {
    val strategyReport by viewModel.selectedStrategyReport.collectAsState()
    val report = strategyReport
    if (report == null) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text("Trade History") },
                    navigationIcon = {
                        IconButton(onClick = { navController.popBackStack() }) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                        }
                    }
                )
            }
        ) { padding ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = "Open this screen from Reports by tapping \"View full table\" on a strategy.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
        return
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = report.strategyName,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Text(
                            text = "${report.symbol} • ${report.strategyType ?: ""}",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = {
                        viewModel.setSelectedStrategyReport(null)
                        navController.popBackStack()
                    }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = Spacing.ScreenPadding)
                .verticalScroll(rememberScrollState())
        ) {
            Spacer(modifier = Modifier.height(Spacing.Medium))
            StrategySummaryCard(strategyReport = report)
            Spacer(modifier = Modifier.height(Spacing.Medium))
            Text(
                text = "Trade History (${report.trades.size} trades)",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(Spacing.Medium))
            if (report.trades.isEmpty()) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                    )
                ) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(32.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "No trades in this period",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            } else {
                FullTradesTable(trades = report.trades)
            }
            Spacer(modifier = Modifier.height(Spacing.ScreenPadding * 2))
        }
    }
}

@Composable
private fun StrategySummaryCard(strategyReport: StrategyReportDto) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f)
        )
    ) {
        Column(
            modifier = Modifier.padding(Spacing.Medium),
            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        "Net PnL",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        FormatUtils.formatCurrency(strategyReport.netPnl),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = if (strategyReport.netPnl >= 0)
                            MaterialTheme.colorScheme.primary
                        else
                            MaterialTheme.colorScheme.error
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(Spacing.Large)) {
                    SummaryChip("Trades", "${strategyReport.totalTrades}")
                    SummaryChip("Win Rate", formatWinRate(strategyReport.winRate))
                    SummaryChip("W/L", "${strategyReport.wins}/${strategyReport.losses}")
                }
            }
            HorizontalDivider()
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("Profit", style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(FormatUtils.formatCurrency(strategyReport.totalProfitUsd),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                        color = MaterialTheme.colorScheme.primary)
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("Loss", style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(FormatUtils.formatCurrency(strategyReport.totalLossUsd),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                        color = MaterialTheme.colorScheme.error)
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("Fees", style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(FormatUtils.formatCurrency(strategyReport.totalFee + strategyReport.totalFundingFee),
                        style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}

@Composable
private fun SummaryChip(label: String, value: String) {
    Surface(
        shape = MaterialTheme.shapes.small,
        color = MaterialTheme.colorScheme.surfaceVariant
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(label, style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun FullTradesTable(trades: List<TradeReportDto>) {
    val horizontalScrollState = rememberScrollState()
    val columnHeaders = listOf(
        "Trade ID" to ColWidthNarrow,
        "Symbol" to ColWidthNarrow,
        "Side" to ColWidthNarrow,
        "Entry Time" to ColWidthWide,
        "Entry Price" to ColWidthNarrow,
        "Exit Time" to ColWidthWide,
        "Exit Price" to ColWidthNarrow,
        "Qty" to ColWidthNarrow,
        "Leverage" to ColWidthNarrow,
        "Fee" to ColWidthNarrow,
        "Funding" to ColWidthNarrow,
        "PnL USD" to ColWidthNarrow,
        "PnL %" to ColWidthNarrow,
        "Exit Reason" to ColWidthWide,
        "Init Margin" to ColWidthNarrow,
        "Margin Type" to ColWidthNarrow,
        "Notional" to ColWidthNarrow,
        "Entry Ord" to ColWidthNarrow,
        "Exit Ord" to ColWidthNarrow
    )
    
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RectangleShape,
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        )
    ) {
        Column(modifier = Modifier.horizontalScroll(horizontalScrollState)) {
            // Header row
            Surface(
                color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.6f),
                shape = RectangleShape
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    columnHeaders.forEach { (title, width) ->
                        Box(
                            modifier = Modifier.width(width).padding(horizontal = 4.dp),
                            contentAlignment = Alignment.CenterStart
                        ) {
                            Text(
                                text = title,
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }
                }
            }
            HorizontalDivider()
            trades.forEachIndexed { index, trade ->
                Surface(
                    color = if (index % 2 == 0)
                        MaterialTheme.colorScheme.surface
                    else
                        MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f),
                    shape = RectangleShape
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 8.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        TableCell(ColWidthNarrow, trade.tradeId.take(8) + "…")
                        TableCell(ColWidthNarrow, trade.symbol)
                        TableCell(ColWidthNarrow, trade.side)
                        TableCell(ColWidthWide, trade.entryTime?.take(19) ?: "—")
                        TableCell(ColWidthNarrow, "%.4f".format(trade.entryPrice))
                        TableCell(ColWidthWide, trade.exitTime?.take(19) ?: "—")
                        TableCell(ColWidthNarrow, trade.exitPrice?.let { "%.4f".format(it) } ?: "—")
                        TableCell(ColWidthNarrow, "%.4f".format(trade.quantity))
                        TableCell(ColWidthNarrow, "${trade.leverage}x")
                        TableCell(ColWidthNarrow, FormatUtils.formatCurrency(trade.feePaid))
                        TableCell(ColWidthNarrow, FormatUtils.formatCurrency(trade.fundingFee))
                        TableCell(
                            ColWidthNarrow,
                            FormatUtils.formatCurrency(trade.pnlUsd),
                            if (trade.pnlUsd >= 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                        )
                        TableCell(ColWidthNarrow, "%.2f%%".format(trade.pnlPct))
                        TableCell(ColWidthWide, trade.exitReason ?: "—")
                        TableCell(ColWidthNarrow, trade.initialMargin?.let { FormatUtils.formatCurrency(it) } ?: "—")
                        TableCell(ColWidthNarrow, trade.marginType ?: "—")
                        TableCell(ColWidthNarrow, trade.notionalValue?.let { FormatUtils.formatCurrency(it) } ?: "—")
                        TableCell(ColWidthNarrow, trade.entryOrderId?.toString() ?: "—")
                        TableCell(ColWidthNarrow, trade.exitOrderId?.toString() ?: "—")
                    }
                }
                if (index < trades.size - 1) {
                    HorizontalDivider(modifier = Modifier.padding(start = 8.dp, end = 8.dp))
                }
            }
        }
    }
}

@Composable
private fun RowScope.TableCell(
    width: androidx.compose.ui.unit.Dp,
    value: String,
    color: Color = MaterialTheme.colorScheme.onSurface
) {
    Box(
        modifier = Modifier
            .width(width)
            .padding(horizontal = 4.dp),
        contentAlignment = Alignment.CenterStart
    ) {
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall,
            color = color,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}
