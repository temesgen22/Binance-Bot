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
    onManualClose: ((Position) -> Unit)? = null,
    manualCloseInProgressStrategyId: String? = null,
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
                    key = { "${it.symbol}_${it.positionSide}_${it.strategyId ?: "manual"}_${it.accountId.orEmpty()}" }
                ) { position ->
                    val compositeKey = "${position.accountId?.takeIf { it.isNotBlank() } ?: "default"}|${position.strategyId?.takeIf { it.isNotBlank() } ?: "manual_${position.symbol}"}"
                    BinanceStylePositionRow(
                        position = position,
                        onStrategyClick = onStrategyClick,
                        onManualClose = onManualClose,
                        isManualCloseInProgress = (manualCloseInProgressStrategyId != null && compositeKey == manualCloseInProgressStrategyId)
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
    onStrategyClick: ((strategyId: String) -> Unit)? = null,
    onManualClose: ((Position) -> Unit)? = null,
    isManualCloseInProgress: Boolean = false
) {
    val isLong = position.isLong
    val sideColor = if (isLong) LongGreen else ShortRed
    val cardBg = if (isLong) LongBg else ShortBg
    val pnlColor = if (position.unrealizedPnL >= 0) LongGreen else ShortRed
    val hasStrategy = !position.strategyId.isNullOrBlank()
    val isManualPosition = position.strategyId?.startsWith("manual_") == true
    val isExternalPosition = position.strategyId?.startsWith("external_") == true
    var showManualCloseConfirm by remember { mutableStateOf(false) }

    if (showManualCloseConfirm) {
        AlertDialog(
            onDismissRequest = { showManualCloseConfirm = false },
            title = { Text("Manual Close") },
            text = {
                Text(
                    "Manually close ${position.symbol} ${position.positionSide} and record exit reason as MANUAL?"
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showManualCloseConfirm = false
                        position.strategyId?.let { onManualClose?.invoke(position) }
                    }
                ) {
                    Text("Close position", color = ShortRed)
                }
            },
            dismissButton = {
                TextButton(onClick = { showManualCloseConfirm = false }) {
                    Text("Cancel", color = MaterialTheme.colorScheme.onSurface)
                }
            }
        )
    }

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
                    Text(
                        text = "Account: ${position.accountId?.takeIf { it.isNotBlank() } ?: "default" }",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
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
                // Owner label: same as web app — Manual Trade, External, strategy name, "Strategy" (id but no name), or External (no id)
                val ownerLabel = when {
                    isManualPosition -> "Manual Trade"
                    isExternalPosition -> "External"
                    position.strategyName?.isNotBlank() == true -> position.strategyName
                    position.strategyId?.isNotBlank() == true -> "Strategy"
                    else -> "External"
                }
                
                // Owner: strategy that owns this position (from backend matching); External = opened on Binance outside bot
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .then(
                            if (hasStrategy && !isManualPosition && !isExternalPosition && onStrategyClick != null)
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
                        text = ownerLabel,
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.Medium,
                        color = when {
                            isManualPosition -> Color(0xFF667EEA)
                            isExternalPosition -> MaterialTheme.colorScheme.onSurfaceVariant
                            hasStrategy -> MaterialTheme.colorScheme.primary
                            else -> MaterialTheme.colorScheme.onSurfaceVariant
                        }
                    )
                }
            }

            // Close button - for strategy-owned and manual positions only; external positions cannot be closed via app
            if ((hasStrategy || isManualPosition) && !isExternalPosition && onManualClose != null) {
                Spacer(modifier = Modifier.height(8.dp))
                Button(
                    onClick = { showManualCloseConfirm = true },
                    enabled = !isManualCloseInProgress,
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = ShortRed)
                ) {
                    Text(
                        if (isManualCloseInProgress) "Closing…" else "Close"
                    )
                }
            }
        }
    }
}

// Computed property to check if position is manual
private val Position.isManualPosition: Boolean
    get() = strategyId?.startsWith("manual_") == true

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
