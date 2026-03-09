package com.binancebot.mobile.presentation.screens.trades

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.binancebot.mobile.domain.model.Position
import com.binancebot.mobile.presentation.components.SwipeRefreshBox
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils

/**
 * Open positions list – Binance Futures style: compact rows with symbol, side, PnL, and key metrics.
 */
@Composable
fun PositionsTab(
    positions: List<Position>,
    isLoading: Boolean,
    onRefresh: () -> Unit,
    modifier: Modifier = Modifier
) {
    SwipeRefreshBox(
        isRefreshing = isLoading,
        onRefresh = onRefresh,
        modifier = modifier
    ) {
        if (positions.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    Text(
                        text = "No open positions",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = "Positions will appear here when you have open futures positions",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(horizontal = Spacing.ScreenPadding, vertical = Spacing.Small),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                items(
                    items = positions,
                    key = { "${it.symbol}_${it.strategyId ?: "manual"}_${it.accountId.orEmpty()}" }
                ) { position ->
                    BinanceStylePositionRow(position = position)
                }
            }
        }
    }
}

/**
 * Single position row in Binance Futures style: symbol + side + unrealized PnL on top; Entry, Mark, Margin, Leverage, Liq in a compact block.
 */
@Composable
fun BinanceStylePositionRow(position: Position) {
    val isLong = position.isLong
    val surfaceColor = if (isLong)
        MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.25f)
    else
        MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.25f)
    val sideColor = if (isLong) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
    val pnlColor = if (position.unrealizedPnL >= 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = surfaceColor),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Row 1: Symbol | Side | Unrealized PnL
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = position.symbol,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    position.strategyName?.takeIf { it.isNotBlank() }?.let { name ->
                        Text(
                            text = name,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    position.accountId?.takeIf { it.isNotBlank() }?.let { id ->
                        Text(
                            text = id,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                Surface(
                    shape = RoundedCornerShape(6.dp),
                    color = sideColor.copy(alpha = 0.2f)
                ) {
                    Text(
                        text = position.positionSide,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = sideColor
                    )
                }
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text(
                    text = FormatUtils.formatCurrency(position.unrealizedPnL),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = pnlColor
                )
            }

            // Row 2: Key metrics in a compact grid (Binance-style)
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))
                    .padding(horizontal = 12.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    MetricChip("Size", String.format("%.4f", position.positionSize))
                    MetricChip("Entry", FormatUtils.formatCurrency(position.entryPrice))
                    MetricChip("Mark", FormatUtils.formatCurrency(position.currentPrice))
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    MetricChip("Leverage", "${position.leverage}x")
                    position.initialMargin?.takeIf { it >= 0 }?.let { margin ->
                        MetricChip("Margin (USDT)", FormatUtils.formatCurrency(margin))
                    }
                    position.liquidationPrice?.takeIf { it > 0 }?.let { liq ->
                        MetricChip("Liq. Price", FormatUtils.formatCurrency(liq))
                    }
                }
                position.marginType?.takeIf { it.isNotBlank() }?.let { mt ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Start
                    ) {
                        MetricChip("Margin Type", mt)
                    }
                }
            }
        }
    }
}

@Composable
private fun MetricChip(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            fontSize = 10.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Medium
        )
    }
}
