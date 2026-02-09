package com.binancebot.mobile.presentation.screens.trades

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.OverallStats

@Composable
fun OverallStatsCard(
    stats: OverallStats,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier,
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.CardPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            Text(
                text = "Overall Statistics",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )
            
            Divider()
            
            // First Row: PnL Metrics
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                StatItem(
                    label = "Total PnL",
                    value = FormatUtils.formatCurrency(stats.totalPnL),
                    isPositive = stats.totalPnL >= 0
                )
                StatItem(
                    label = "Realized PnL",
                    value = FormatUtils.formatCurrency(stats.realizedPnL),
                    isPositive = stats.realizedPnL >= 0
                )
                StatItem(
                    label = "Unrealized PnL",
                    value = FormatUtils.formatCurrency(stats.unrealizedPnL),
                    isPositive = stats.unrealizedPnL >= 0
                )
            }
            
            Divider()
            
            // Second Row: Trade Metrics
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                StatItem(
                    label = "Total Trades",
                    value = "${stats.totalTrades}",
                    isPositive = null
                )
                StatItem(
                    label = "Win Rate",
                    value = "${String.format("%.2f", stats.winRate)}%",
                    isPositive = stats.winRate >= 50
                )
                StatItem(
                    label = "Active Positions",
                    value = "${stats.activePositions}",
                    isPositive = null
                )
            }
            
            // Wins/Losses
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                StatItem(
                    label = "Wins",
                    value = "${stats.winningTrades}",
                    isPositive = true
                )
                StatItem(
                    label = "Losses",
                    value = "${stats.losingTrades}",
                    isPositive = false
                )
            }
        }
    }
}

@Composable
private fun StatItem(
    label: String,
    value: String,
    isPositive: Boolean?,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(modifier = Modifier.height(Spacing.Tiny))
        Text(
            text = value,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = when (isPositive) {
                true -> MaterialTheme.colorScheme.primary
                false -> MaterialTheme.colorScheme.error
                null -> MaterialTheme.colorScheme.onSurface
            }
        )
    }
}

