package com.binancebot.mobile.presentation.screens.settings

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
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.viewmodel.SettingsViewModel
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NotificationSettingsScreen(
    navController: NavController,
    settingsViewModel: SettingsViewModel = hiltViewModel()
) {
    val notificationsEnabled by settingsViewModel.notificationsEnabled.collectAsState(initial = true)
    val tradesEnabled by settingsViewModel.tradesEnabled.collectAsState(initial = true)
    val alertsEnabled by settingsViewModel.alertsEnabled.collectAsState(initial = true)
    val strategyEnabled by settingsViewModel.strategyEnabled.collectAsState(initial = true)
    val systemEnabled by settingsViewModel.systemEnabled.collectAsState(initial = false)
    val tradePnLThreshold by settingsViewModel.tradePnLThreshold.collectAsState(initial = 100.0)
    
    // Per-category sound/vibration settings
    val tradesSoundEnabled by settingsViewModel.tradesSoundEnabled.collectAsState(initial = true)
    val tradesVibrationEnabled by settingsViewModel.tradesVibrationEnabled.collectAsState(initial = true)
    val alertsSoundEnabled by settingsViewModel.alertsSoundEnabled.collectAsState(initial = true)
    val alertsVibrationEnabled by settingsViewModel.alertsVibrationEnabled.collectAsState(initial = true)
    val strategySoundEnabled by settingsViewModel.strategySoundEnabled.collectAsState(initial = true)
    val strategyVibrationEnabled by settingsViewModel.strategyVibrationEnabled.collectAsState(initial = true)
    val systemSoundEnabled by settingsViewModel.systemSoundEnabled.collectAsState(initial = false)
    val systemVibrationEnabled by settingsViewModel.systemVibrationEnabled.collectAsState(initial = false)
    
    val scope = rememberCoroutineScope()
    var pnlThresholdText by remember { mutableStateOf(tradePnLThreshold.toString()) }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Notification Settings") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
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
                .verticalScroll(rememberScrollState())
                .padding(Spacing.ScreenPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            // Global Toggle
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(Spacing.Medium),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Enable Notifications",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Master switch for all notifications",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        Switch(
                            checked = notificationsEnabled,
                            onCheckedChange = { enabled ->
                                scope.launch {
                                    settingsViewModel.setNotificationsEnabled(enabled)
                                }
                            }
                        )
                    }
                }
            }
            
            if (notificationsEnabled) {
                // Trade Notifications
                NotificationCategoryCard(
                    title = "Trade Notifications",
                    enabled = tradesEnabled,
                    onEnabledChange = { scope.launch { settingsViewModel.setTradesEnabled(it) } },
                    soundEnabled = tradesSoundEnabled,
                    onSoundChange = { scope.launch { settingsViewModel.setTradesSoundEnabled(it) } },
                    vibrationEnabled = tradesVibrationEnabled,
                    onVibrationChange = { scope.launch { settingsViewModel.setTradesVibrationEnabled(it) } }
                ) {
                    OutlinedTextField(
                        value = pnlThresholdText,
                        onValueChange = { 
                            pnlThresholdText = it
                            it.toDoubleOrNull()?.let { threshold ->
                                scope.launch { settingsViewModel.setTradePnLThreshold(threshold) }
                            }
                        },
                        label = { Text("PnL Threshold (USD)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                }
                
                // Alert Notifications
                NotificationCategoryCard(
                    title = "Alert Notifications",
                    enabled = alertsEnabled,
                    onEnabledChange = { scope.launch { settingsViewModel.setAlertsEnabled(it) } },
                    soundEnabled = alertsSoundEnabled,
                    onSoundChange = { scope.launch { settingsViewModel.setAlertsSoundEnabled(it) } },
                    vibrationEnabled = alertsVibrationEnabled,
                    onVibrationChange = { scope.launch { settingsViewModel.setAlertsVibrationEnabled(it) } }
                )
                
                // Strategy Notifications
                NotificationCategoryCard(
                    title = "Strategy Notifications",
                    enabled = strategyEnabled,
                    onEnabledChange = { scope.launch { settingsViewModel.setStrategyEnabled(it) } },
                    soundEnabled = strategySoundEnabled,
                    onSoundChange = { scope.launch { settingsViewModel.setStrategySoundEnabled(it) } },
                    vibrationEnabled = strategyVibrationEnabled,
                    onVibrationChange = { scope.launch { settingsViewModel.setStrategyVibrationEnabled(it) } }
                )
                
                // System Notifications
                NotificationCategoryCard(
                    title = "System Notifications",
                    enabled = systemEnabled,
                    onEnabledChange = { scope.launch { settingsViewModel.setSystemEnabled(it) } },
                    soundEnabled = systemSoundEnabled,
                    onSoundChange = { scope.launch { settingsViewModel.setSystemSoundEnabled(it) } },
                    vibrationEnabled = systemVibrationEnabled,
                    onVibrationChange = { scope.launch { settingsViewModel.setSystemVibrationEnabled(it) } }
                )
            }
        }
    }
}

@Composable
private fun NotificationCategoryCard(
    title: String,
    enabled: Boolean,
    onEnabledChange: (Boolean) -> Unit,
    soundEnabled: Boolean,
    onSoundChange: (Boolean) -> Unit,
    vibrationEnabled: Boolean,
    onVibrationChange: (Boolean) -> Unit,
    content: @Composable ColumnScope.() -> Unit = {}
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                Switch(
                    checked = enabled,
                    onCheckedChange = onEnabledChange
                )
            }
            
            if (enabled) {
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Sound",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Switch(
                        checked = soundEnabled,
                        onCheckedChange = onSoundChange
                    )
                }
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Vibration",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Switch(
                        checked = vibrationEnabled,
                        onCheckedChange = onVibrationChange
                    )
                }
                
                content()
            }
        }
    }
}





