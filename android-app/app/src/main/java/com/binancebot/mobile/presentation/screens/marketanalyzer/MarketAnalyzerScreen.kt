package com.binancebot.mobile.presentation.screens.marketanalyzer

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
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
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.viewmodel.MarketAnalyzerViewModel
import com.binancebot.mobile.presentation.viewmodel.MarketAnalyzerUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MarketAnalyzerScreen(
    navController: NavController,
    viewModel: MarketAnalyzerViewModel = hiltViewModel()
) {
    val analysis by viewModel.analysis.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
    // Form state
    var symbol by remember { mutableStateOf("BTCUSDT") }
    var interval by remember { mutableStateOf("5m") }
    var showAdvancedOptions by remember { mutableStateOf(false) }
    
    // Advanced options
    var lookbackPeriod by remember { mutableStateOf("150") }
    var emaFastPeriod by remember { mutableStateOf("20") }
    var emaSlowPeriod by remember { mutableStateOf("50") }
    var maxEmaSpreadPct by remember { mutableStateOf("0.005") }
    var rsiPeriod by remember { mutableStateOf("14") }
    var swingPeriod by remember { mutableStateOf("5") }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Market Analyzer") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        when (uiState) {
            is MarketAnalyzerUiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        CircularProgressIndicator()
                        Text(
                            text = "Analyzing market...",
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
            }
            is MarketAnalyzerUiState.Error -> {
                ErrorHandler(
                    message = (uiState as MarketAnalyzerUiState.Error).message,
                    onRetry = {
                        viewModel.analyzeMarket(
                            symbol = symbol,
                            interval = interval,
                            lookbackPeriod = lookbackPeriod.toIntOrNull() ?: 150,
                            emaFastPeriod = emaFastPeriod.toIntOrNull() ?: 20,
                            emaSlowPeriod = emaSlowPeriod.toIntOrNull() ?: 50,
                            maxEmaSpreadPct = maxEmaSpreadPct.toDoubleOrNull() ?: 0.005,
                            rsiPeriod = rsiPeriod.toIntOrNull() ?: 14,
                            swingPeriod = swingPeriod.toIntOrNull() ?: 5
                        )
                    },
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
                        .verticalScroll(rememberScrollState())
                        .padding(Spacing.ScreenPadding),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    // Analysis Form
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                    ) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(Spacing.Medium),
                            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                        ) {
                            Text(
                                text = "Market Analysis Configuration",
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold
                            )
                            
                            // Symbol Input
                            OutlinedTextField(
                                value = symbol,
                                onValueChange = { symbol = it.uppercase() },
                                label = { Text("Symbol (e.g., BTCUSDT)") },
                                modifier = Modifier.fillMaxWidth(),
                                singleLine = true,
                                leadingIcon = {
                                    Icon(Icons.Default.CurrencyBitcoin, contentDescription = null)
                                }
                            )
                            
                            // Interval Selection
                            var expandedInterval by remember { mutableStateOf(false) }
                            val intervals = listOf("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M")
                            
                            ExposedDropdownMenuBox(
                                expanded = expandedInterval,
                                onExpandedChange = { expandedInterval = !expandedInterval }
                            ) {
                                OutlinedTextField(
                                    value = interval,
                                    onValueChange = {},
                                    readOnly = true,
                                    label = { Text("Timeframe") },
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .menuAnchor(),
                                    trailingIcon = {
                                        ExposedDropdownMenuDefaults.TrailingIcon(expanded = expandedInterval)
                                    }
                                )
                                ExposedDropdownMenu(
                                    expanded = expandedInterval,
                                    onDismissRequest = { expandedInterval = false }
                                ) {
                                    intervals.forEach { item ->
                                        DropdownMenuItem(
                                            text = { Text(item) },
                                            onClick = {
                                                interval = item
                                                expandedInterval = false
                                            }
                                        )
                                    }
                                }
                            }
                            
                            // Advanced Options Toggle
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "Advanced Options",
                                    style = MaterialTheme.typography.bodyMedium
                                )
                                Switch(
                                    checked = showAdvancedOptions,
                                    onCheckedChange = { showAdvancedOptions = it }
                                )
                            }
                            
                            // Advanced Options
                            if (showAdvancedOptions) {
                                Column(
                                    verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                                ) {
                                    OutlinedTextField(
                                        value = lookbackPeriod,
                                        onValueChange = { lookbackPeriod = it },
                                        label = { Text("Lookback Period") },
                                        modifier = Modifier.fillMaxWidth(),
                                        singleLine = true
                                    )
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                                    ) {
                                        OutlinedTextField(
                                            value = emaFastPeriod,
                                            onValueChange = { emaFastPeriod = it },
                                            label = { Text("EMA Fast Period") },
                                            modifier = Modifier.weight(1f),
                                            singleLine = true
                                        )
                                        OutlinedTextField(
                                            value = emaSlowPeriod,
                                            onValueChange = { emaSlowPeriod = it },
                                            label = { Text("EMA Slow Period") },
                                            modifier = Modifier.weight(1f),
                                            singleLine = true
                                        )
                                    }
                                    OutlinedTextField(
                                        value = maxEmaSpreadPct,
                                        onValueChange = { maxEmaSpreadPct = it },
                                        label = { Text("Max EMA Spread %") },
                                        modifier = Modifier.fillMaxWidth(),
                                        singleLine = true
                                    )
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                                    ) {
                                        OutlinedTextField(
                                            value = rsiPeriod,
                                            onValueChange = { rsiPeriod = it },
                                            label = { Text("RSI Period") },
                                            modifier = Modifier.weight(1f),
                                            singleLine = true
                                        )
                                        OutlinedTextField(
                                            value = swingPeriod,
                                            onValueChange = { swingPeriod = it },
                                            label = { Text("Swing Period") },
                                            modifier = Modifier.weight(1f),
                                            singleLine = true
                                        )
                                    }
                                }
                            }
                            
                            // Analyze Button
                            Button(
                                onClick = {
                                    viewModel.analyzeMarket(
                                        symbol = symbol,
                                        interval = interval,
                                        lookbackPeriod = lookbackPeriod.toIntOrNull() ?: 150,
                                        emaFastPeriod = emaFastPeriod.toIntOrNull() ?: 20,
                                        emaSlowPeriod = emaSlowPeriod.toIntOrNull() ?: 50,
                                        maxEmaSpreadPct = maxEmaSpreadPct.toDoubleOrNull() ?: 0.005,
                                        rsiPeriod = rsiPeriod.toIntOrNull() ?: 14,
                                        swingPeriod = swingPeriod.toIntOrNull() ?: 20
                                    )
                                },
                                modifier = Modifier.fillMaxWidth(),
                                enabled = symbol.isNotBlank() && uiState !is MarketAnalyzerUiState.Loading
                            ) {
                                Icon(Icons.Default.Analytics, contentDescription = null)
                                Spacer(modifier = Modifier.width(Spacing.Small))
                                Text("Analyze Market")
                            }
                        }
                    }
                    
                    // Analysis Results
                    analysis?.let { result ->
                        AnalysisResultsCard(analysis = result)
                    }
                }
            }
        }
    }
}

@Composable
fun AnalysisResultsCard(
    analysis: com.binancebot.mobile.data.remote.dto.MarketAnalysisResponse
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(
            containerColor = when (analysis.marketCondition.uppercase()) {
                "TRENDING" -> MaterialTheme.colorScheme.primaryContainer
                "SIDEWAYS" -> MaterialTheme.colorScheme.secondaryContainer
                else -> MaterialTheme.colorScheme.surfaceVariant
            }
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "📊 Market Analysis Results",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                Surface(
                    shape = MaterialTheme.shapes.small,
                    color = when (analysis.marketCondition.uppercase()) {
                        "TRENDING" -> MaterialTheme.colorScheme.primary
                        "SIDEWAYS" -> MaterialTheme.colorScheme.secondary
                        else -> MaterialTheme.colorScheme.surfaceVariant
                    }
                ) {
                    Text(
                        text = analysis.marketCondition.replaceFirstChar { it.uppercase() },
                        modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            
            HorizontalDivider()
            
            // Key Metrics
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text(
                        text = "Current Price",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = String.format("$%.2f", analysis.currentPrice),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
                Column {
                    Text(
                        text = "Confidence",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = String.format("%.1f%%", analysis.confidence * 100),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            
            // Recommendation
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant
                )
            ) {
                Column(
                    modifier = Modifier.padding(Spacing.Medium)
                ) {
                    Text(
                        text = "Recommendation",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(Spacing.Tiny))
                    Text(
                        text = analysis.recommendation,
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }
            
            // Indicators Section
            if (analysis.indicators.isNotEmpty()) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(Spacing.Medium),
                        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                    ) {
                        Text(
                            text = "Technical Indicators",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold
                        )
                        analysis.indicators.forEach { (key, value) ->
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(
                                    text = key.replace("_", " ").replaceFirstChar { it.uppercase() },
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Text(
                                    text = when (value) {
                                        is Double -> String.format("%.4f", value)
                                        is Float -> String.format("%.4f", value)
                                        is Number -> value.toString()
                                        else -> value.toString()
                                    },
                                    style = MaterialTheme.typography.bodySmall,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                    }
                }
            }
            
            // Trend Info Section
            if (analysis.trendInfo.isNotEmpty()) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(Spacing.Medium),
                        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                    ) {
                        Text(
                            text = "Trend Information",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold
                        )
                        analysis.trendInfo.forEach { (key, value) ->
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(
                                    text = key.replace("_", " ").replaceFirstChar { it.uppercase() },
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Text(
                                    text = when (value) {
                                        is Double -> String.format("%.4f", value)
                                        is Float -> String.format("%.4f", value)
                                        is Number -> value.toString()
                                        else -> value.toString()
                                    },
                                    style = MaterialTheme.typography.bodySmall,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                    }
                }
            }
            
            // Range Info Section (if available)
            analysis.rangeInfo?.let { rangeInfo ->
                if (rangeInfo.isNotEmpty()) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                    ) {
                        Column(
                            modifier = Modifier.padding(Spacing.Medium),
                            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                        ) {
                            Text(
                                text = "Range Information",
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold
                            )
                            rangeInfo.forEach { (key, value) ->
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text(
                                        text = key.replace("_", " ").replaceFirstChar { it.uppercase() },
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Text(
                                        text = when (value) {
                                            is Double -> String.format("%.4f", value)
                                            is Float -> String.format("%.4f", value)
                                            is Number -> value.toString()
                                            else -> value.toString()
                                        },
                                        style = MaterialTheme.typography.bodySmall,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                            }
                        }
                    }
                }
            }
            
            // Volume Analysis Section (if available)
            analysis.volumeAnalysis?.let { volumeAnalysis ->
                if (volumeAnalysis.isNotEmpty()) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                    ) {
                        Column(
                            modifier = Modifier.padding(Spacing.Medium),
                            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                        ) {
                            Text(
                                text = "Volume Analysis",
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold
                            )
                            volumeAnalysis.forEach { (key, value) ->
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text(
                                        text = key.replace("_", " ").replaceFirstChar { it.uppercase() },
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Text(
                                        text = when (value) {
                                            is Double -> String.format("%.4f", value)
                                            is Float -> String.format("%.4f", value)
                                            is Number -> value.toString()
                                            else -> value.toString()
                                        },
                                        style = MaterialTheme.typography.bodySmall,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
