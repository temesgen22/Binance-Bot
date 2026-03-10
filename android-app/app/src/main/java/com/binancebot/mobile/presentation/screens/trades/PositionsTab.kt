package com.binancebot.mobile.presentation.screens.trades

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.binancebot.mobile.domain.model.Position
import com.binancebot.mobile.presentation.components.SwipeRefreshBox
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils

// Binance-style colors: Long = green, Short = red (matches webapp)
private val LongGreen = Color(0xFF28A745)
private val ShortRed = Color(0xFFDC3545)
private val LongBg = Color(0xFFE8F5E9)
private val ShortBg = Color(0xFFFFEBEE)

/**
 * Open positions list – Binance Futures style: Long = green, Short = red; prices with decimals like Binance; all parameters shown.
 * Strategy row shows strategy name or "Not matched" (like webapp); click navigates to strategy detail when position has a strategy.
 */
@Composable
fun PositionsTab(
    positions: List<Position>,
    isLoading: Boolean,
    onRefresh: () -> Unit,
    onStrategyClick: ((strategyId: String) -> Unit)? = null,
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
                    BinanceStylePositionRow(
                        position = position,
                        onStrategyClick = onStrategyClick
                    )
                }
            }
        }
    }
}

/**
 * Single position row: Binance colors (Long=green, Short=red), prices with decimals (formatPrice), all parameters displayed.
 * Strategy shown as in webapp (name or "Not matched"); click navigates to strategy detail when position has a strategy.
 */
@Composable
fun BinanceStylePositionRow(
    position: Position,
    onStrategyClick: ((strategyId: String) -> Unit)? = null
) {
    val isLong = position.isLong
    val sideColor = if (isLong) LongGreen else ShortRed
    val cardBg = if (isLong) LongBg else ShortBg
    val pnlColor = if (position.unrealizedPnL >= 0) LongGreen else ShortRed
    val strategyLabel = position.strategyName?.takeIf { it.isNotBlank() } ?: "Not matched"
    val hasStrategy = !position.strategyId.isNullOrBlank()

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = cardBg),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Header: Symbol | Side badge | Unrealized PnL
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
                    position.accountId?.takeIf { it.isNotBlank() }?.let { id ->
                        Text(
                            text = "Account: $id",
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

            // All parameters in a single block (Binance-style), always visible
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f))
                    .padding(horizontal = 12.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                // Row 1: Size, Entry Price, Mark Price (prices with decimals like Binance)
                PositionParamRow("Size", String.format("%.4f", position.positionSize))
                PositionParamRow("Entry Price", FormatUtils.formatPrice(position.entryPrice))
                PositionParamRow("Mark Price", FormatUtils.formatPrice(position.currentPrice))
                PositionParamRow("Leverage", "${position.leverage}x")
                // Liquidation Price – show value or "—"
                PositionParamRow(
                    "Liquidation Price",
                    position.liquidationPrice?.takeIf { it > 0 }?.let { FormatUtils.formatPrice(it) } ?: "—"
                )
                // Margin (USDT) – always show row
                PositionParamRow(
                    "Margin (USDT)",
                    position.initialMargin?.takeIf { it >= 0 }?.let { FormatUtils.formatCurrency(it) } ?: "—"
                )
                // Margin Type
                PositionParamRow(
                    "Margin Type",
                    position.marginType?.takeIf { it.isNotBlank() } ?: "—"
                )
                // Owner: strategy that owns this position (from backend matching); "Not matched" if manual/unowned
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .then(
                            if (hasStrategy && onStrategyClick != null)
                                Modifier.clickable { position.strategyId?.let { onStrategyClick(it) } }
                            else Modifier
                        ),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Owner",
                        style = MaterialTheme.typography.labelSmall,
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = strategyLabel,
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.Medium,
                        color = if (hasStrategy) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

@Composable
private fun PositionParamRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            fontSize = 11.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Medium
        )
    }
}
