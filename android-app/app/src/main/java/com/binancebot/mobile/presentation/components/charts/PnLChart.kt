package com.binancebot.mobile.presentation.components.charts

import androidx.compose.foundation.layout.*
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

/**
 * PnL Line Chart Component
 */
@Composable
fun PnLChart(
    data: List<Pair<String, Float>>, // Date label, PnL value
    modifier: Modifier = Modifier,
    title: String = "PnL Over Time"
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.CardPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
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
                        text = "No data available",
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
                                    lineColor = MaterialTheme.colorScheme.primary,
                                    lineThickness = 3.dp
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
                                if (index >= 0 && index < data.size) {
                                    data[index].first
                                } else {
                                    ""
                                }
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

