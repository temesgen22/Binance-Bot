package com.binancebot.mobile.presentation.components.charts

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.presentation.theme.Spacing
import com.patrykandpatrick.vico.compose.axis.horizontal.bottomAxis
import com.patrykandpatrick.vico.compose.axis.vertical.startAxis
import com.patrykandpatrick.vico.compose.chart.Chart
import com.patrykandpatrick.vico.compose.chart.line.lineChart
import com.patrykandpatrick.vico.compose.chart.line.lineSpec
import com.patrykandpatrick.vico.compose.style.ProvideChartStyle
import com.patrykandpatrick.vico.core.axis.formatter.AxisValueFormatter
import com.patrykandpatrick.vico.core.entry.ChartEntryModelProducer
import com.patrykandpatrick.vico.core.entry.entryOf
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * Price line chart from klines (close price over time), similar to web app price chart.
 * klines format: List of [timestampMs, open, high, low, close, volume]
 */
@Composable
fun PriceLineChart(
    klines: List<List<*>>,
    modifier: Modifier = Modifier,
    title: String = "Price (Close)"
) {
    val data = rememberKlinesToChartData(klines)
    Card(
        modifier = modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.CardPadding),
            verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(Spacing.Medium)
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            if (data.isEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(200.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "No price data",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            } else {
                val entries = data.mapIndexed { index, (_, value) ->
                    entryOf(index, value)
                }
                ProvideChartStyle {
                    Chart(
                        chart = lineChart(
                            lines = listOf(
                                lineSpec(
                                    lineColor = MaterialTheme.colorScheme.tertiary,
                                    lineThickness = 2.dp
                                )
                            )
                        ),
                        chartModelProducer = ChartEntryModelProducer(entries),
                        startAxis = startAxis(
                            valueFormatter = AxisValueFormatter { value, _ ->
                                String.format("%.2f", value)
                            }
                        ),
                        bottomAxis = bottomAxis(
                            valueFormatter = AxisValueFormatter { value, _ ->
                                val index = value.toInt()
                                if (index >= 0 && index < data.size) data[index].first else ""
                            }
                        ),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(200.dp)
                    )
                }
            }
        }
    }
}

@Composable
private fun rememberKlinesToChartData(klines: List<List<*>>): List<Pair<String, Float>> {
    return androidx.compose.runtime.remember(klines) {
        if (klines.isEmpty()) emptyList()
        else {
            val formatter = DateTimeFormatter.ofPattern("MM-dd").withZone(ZoneId.systemDefault())
            klines.mapNotNull { k ->
                if (k.size < 5) null
                else {
                    val ts = (k[0] as? Number)?.toLong() ?: null
                    val close = (k[4] as? Number)?.toFloat() ?: null
                    if (ts == null || close == null) null
                    else formatter.format(Instant.ofEpochMilli(ts)) to close
                }
            }
        }
    }
}
