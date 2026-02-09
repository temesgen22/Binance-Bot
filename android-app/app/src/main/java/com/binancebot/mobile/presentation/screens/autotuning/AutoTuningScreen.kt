package com.binancebot.mobile.presentation.screens.autotuning

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import com.binancebot.mobile.presentation.viewmodel.AutoTuningViewModel
import com.binancebot.mobile.presentation.viewmodel.AutoTuningUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AutoTuningScreen(
    navController: NavController,
    viewModel: AutoTuningViewModel = hiltViewModel()
) {
    val strategies by viewModel.strategies.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
    LaunchedEffect(Unit) {
        viewModel.loadStrategies()
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Auto-Tuning") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.loadStrategies() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                }
            )
        }
    ) { padding ->
        when (uiState) {
            is AutoTuningUiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
            is AutoTuningUiState.Error -> {
                ErrorHandler(
                    message = (uiState as AutoTuningUiState.Error).message,
                    onRetry = { viewModel.loadStrategies() },
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                )
            }
            else -> {
                if (strategies.isEmpty()) {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Icon(
                                Icons.Default.Tune,
                                contentDescription = "No strategies",
                                modifier = Modifier.size(64.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(Spacing.Medium))
                            Text(
                                text = "No strategies available",
                                style = MaterialTheme.typography.titleMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(Spacing.Small))
                            Text(
                                text = "Create a strategy first to enable auto-tuning",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding),
                        contentPadding = PaddingValues(Spacing.ScreenPadding),
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        items(strategies) { strategy ->
                            AutoTuningStrategyCard(
                                strategy = strategy,
                                onEnable = { viewModel.enableAutoTuning(strategy.id) },
                                onDisable = { viewModel.disableAutoTuning(strategy.id) },
                                onTuneNow = { viewModel.tuneNow(strategy.id) }
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun AutoTuningStrategyCard(
    strategy: com.binancebot.mobile.domain.model.Strategy,
    onEnable: () -> Unit,
    onDisable: () -> Unit,
    onTuneNow: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
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
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = strategy.name ?: "Unnamed Strategy",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "${strategy.symbol} • ${strategy.strategyType}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                StatusBadge(
                    status = if (strategy.autoTuningEnabled) "Enabled" else "Disabled"
                )
            }
            
            Divider()
            
            // Auto-Tuning Status
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Auto-Tuning Status",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Surface(
                    shape = MaterialTheme.shapes.small,
                    color = if (strategy.autoTuningEnabled) {
                        MaterialTheme.colorScheme.primaryContainer
                    } else {
                        MaterialTheme.colorScheme.surfaceVariant
                    }
                ) {
                    Text(
                        text = if (strategy.autoTuningEnabled) "🟢 Enabled" else "⚪ Disabled",
                        modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            
            // Action Buttons
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                if (strategy.autoTuningEnabled) {
                    Button(
                        onClick = onDisable,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.error
                        )
                    ) {
                        Icon(Icons.Default.Close, null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        Text("Disable")
                    }
                    Button(
                        onClick = onTuneNow,
                        modifier = Modifier.weight(1f)
                    ) {
                        Icon(Icons.Default.Tune, null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        Text("Tune Now")
                    }
                } else {
                    Button(
                        onClick = onEnable,
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.primary
                        )
                    ) {
                        Icon(Icons.Default.Check, null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(Spacing.ExtraSmall))
                        Text("Enable Auto-Tuning")
                    }
                }
            }
            
            // Info Message
            Text(
                text = "Note: Auto-Tuning functionality requires backend API implementation. The endpoints are not currently available.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = Spacing.Small)
            )
        }
    }
}


