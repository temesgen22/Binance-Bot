package com.binancebot.mobile.presentation.screens.risk

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.viewmodel.RiskManagementViewModel

@Composable
fun StrategyRiskConfigDialog(
    strategyId: String,
    strategyName: String?,
    onDismiss: () -> Unit,
    viewModel: RiskManagementViewModel
) {
    val strategyConfig by viewModel.strategyRiskConfig.collectAsState()
    var isLoading by remember(strategyId) { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var configLoaded by remember(strategyId) { mutableStateOf(false) }
    
    LaunchedEffect(strategyId) {
        if (!configLoaded) {
            isLoading = true
            errorMessage = null
            viewModel.loadStrategyRiskConfig(strategyId)
            configLoaded = true
        }
    }
    LaunchedEffect(strategyConfig) {
        isLoading = false
        errorMessage = null
    }
    
    val scope = rememberCoroutineScope()
    val config = strategyConfig
    val isEdit = config != null
    
    // State variables
    var enabled by remember { mutableStateOf(config?.enabled ?: true) }
    var maxDailyLossUsdt by remember { mutableStateOf(config?.maxDailyLossUsdt?.toString() ?: "") }
    var maxDailyLossPct by remember { mutableStateOf((config?.maxDailyLossPct?.times(100))?.toString() ?: "") }
    var maxWeeklyLossUsdt by remember { mutableStateOf(config?.maxWeeklyLossUsdt?.toString() ?: "") }
    var maxWeeklyLossPct by remember { mutableStateOf((config?.maxWeeklyLossPct?.times(100))?.toString() ?: "") }
    var maxDrawdownPct by remember { mutableStateOf((config?.maxDrawdownPct?.times(100))?.toString() ?: "") }
    var overrideAccountLimits by remember { mutableStateOf(config?.overrideAccountLimits ?: false) }
    var useMoreRestrictive by remember { mutableStateOf(config?.useMoreRestrictive ?: true) }
    
    // Update state when config loads
    LaunchedEffect(config) {
        if (config != null) {
            enabled = config.enabled
            maxDailyLossUsdt = config.maxDailyLossUsdt?.toString() ?: ""
            maxDailyLossPct = (config.maxDailyLossPct?.times(100))?.toString() ?: ""
            maxWeeklyLossUsdt = config.maxWeeklyLossUsdt?.toString() ?: ""
            maxWeeklyLossPct = (config.maxWeeklyLossPct?.times(100))?.toString() ?: ""
            maxDrawdownPct = (config.maxDrawdownPct?.times(100))?.toString() ?: ""
            overrideAccountLimits = config.overrideAccountLimits
            useMoreRestrictive = config.useMoreRestrictive
            isLoading = false
        } else {
            // If config is null after loading, it means no config exists (404)
            isLoading = false
        }
    }
    
    fun createUpdatedConfig(): com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto {
        return com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto(
            id = config?.id,
            strategyId = strategyId,
            enabled = enabled,
            maxDailyLossUsdt = maxDailyLossUsdt.toDoubleOrNull(),
            maxDailyLossPct = maxDailyLossPct.toDoubleOrNull()?.div(100),
            maxWeeklyLossUsdt = maxWeeklyLossUsdt.toDoubleOrNull(),
            maxWeeklyLossPct = maxWeeklyLossPct.toDoubleOrNull()?.div(100),
            maxDrawdownPct = maxDrawdownPct.toDoubleOrNull()?.div(100),
            overrideAccountLimits = overrideAccountLimits,
            useMoreRestrictive = useMoreRestrictive
        )
    }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Strategy Risk Config: ${strategyName ?: strategyId}") },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                if (errorMessage != null && !errorMessage!!.contains("404") && !errorMessage!!.contains("not found")) {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        )
                    ) {
                        Text(
                            text = errorMessage ?: "",
                            modifier = Modifier.padding(Spacing.Medium),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                    }
                }
                
                // Enabled toggle
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Enabled")
                    Switch(
                        checked = enabled,
                        onCheckedChange = { enabled = it },
                        enabled = !isLoading
                    )
                }
                
                HorizontalDivider()
                
                // Loss Limits
                Text(
                    text = "Loss Limits",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                OutlinedTextField(
                    value = maxDailyLossUsdt,
                    onValueChange = { maxDailyLossUsdt = it },
                    label = { Text("Max Daily Loss (USDT)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading && enabled
                )
                OutlinedTextField(
                    value = maxDailyLossPct,
                    onValueChange = { maxDailyLossPct = it },
                    label = { Text("Max Daily Loss (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading && enabled
                )
                OutlinedTextField(
                    value = maxWeeklyLossUsdt,
                    onValueChange = { maxWeeklyLossUsdt = it },
                    label = { Text("Max Weekly Loss (USDT)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading && enabled
                )
                OutlinedTextField(
                    value = maxWeeklyLossPct,
                    onValueChange = { maxWeeklyLossPct = it },
                    label = { Text("Max Weekly Loss (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading && enabled
                )
                OutlinedTextField(
                    value = maxDrawdownPct,
                    onValueChange = { maxDrawdownPct = it },
                    label = { Text("Max Drawdown (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading && enabled
                )
                
                HorizontalDivider()
                
                // Priority Mode
                Text(
                    text = "Priority Mode",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Override Account Limits")
                    Switch(
                        checked = overrideAccountLimits,
                        onCheckedChange = { 
                            overrideAccountLimits = it
                            if (it) useMoreRestrictive = false
                        },
                        enabled = !isLoading && enabled
                    )
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Use More Restrictive")
                    Switch(
                        checked = useMoreRestrictive,
                        onCheckedChange = { 
                            useMoreRestrictive = it
                            if (it) overrideAccountLimits = false
                        },
                        enabled = !isLoading && enabled && !overrideAccountLimits
                    )
                }
                Text(
                    text = if (overrideAccountLimits) {
                        "Strategy limits will completely replace account limits"
                    } else if (useMoreRestrictive) {
                        "The most restrictive limit will be used (minimum for losses, maximum for exposure)"
                    } else {
                        "Strategy limits will be ignored, only account limits apply"
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val updatedConfig = createUpdatedConfig()
                    isLoading = true
                    scope.launch {
                        try {
                            if (isEdit) {
                                viewModel.updateStrategyRiskConfig(strategyId, updatedConfig)
                            } else {
                                viewModel.createStrategyRiskConfig(updatedConfig)
                            }
                            // Wait a bit for the operation to complete
                            kotlinx.coroutines.delay(500)
                            isLoading = false
                            onDismiss() // Close dialog after successful save
                        } catch (e: Exception) {
                            isLoading = false
                            errorMessage = e.message
                        }
                    }
                },
                enabled = !isLoading
            ) {
                Text(if (isEdit) "Update" else "Create")
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isLoading
            ) {
                Text("Cancel")
            }
        }
    )
}

/** Callback-based variant for use from list items (no shared ViewModel). */
@Composable
fun StrategyRiskConfigDialogWithCallbacks(
    strategyId: String,
    strategyName: String?,
    onDismiss: () -> Unit,
    initialConfig: com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto?,
    onCreate: (com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto) -> Unit,
    onUpdate: (com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto) -> Unit
) {
    val config = initialConfig
    val isEdit = config != null
    var enabled by remember(config) { mutableStateOf(config?.enabled ?: true) }
    var maxDailyLossUsdt by remember(config) { mutableStateOf(config?.maxDailyLossUsdt?.toString() ?: "") }
    var maxDailyLossPct by remember(config) { mutableStateOf((config?.maxDailyLossPct?.times(100))?.toString() ?: "") }
    var maxWeeklyLossUsdt by remember(config) { mutableStateOf(config?.maxWeeklyLossUsdt?.toString() ?: "") }
    var maxWeeklyLossPct by remember(config) { mutableStateOf((config?.maxWeeklyLossPct?.times(100))?.toString() ?: "") }
    var maxDrawdownPct by remember(config) { mutableStateOf((config?.maxDrawdownPct?.times(100))?.toString() ?: "") }
    var overrideAccountLimits by remember(config) { mutableStateOf(config?.overrideAccountLimits ?: false) }
    var useMoreRestrictive by remember(config) { mutableStateOf(config?.useMoreRestrictive ?: true) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(config) {
        if (config != null) {
            enabled = config.enabled
            maxDailyLossUsdt = config.maxDailyLossUsdt?.toString() ?: ""
            maxDailyLossPct = (config.maxDailyLossPct?.times(100))?.toString() ?: ""
            maxWeeklyLossUsdt = config.maxWeeklyLossUsdt?.toString() ?: ""
            maxWeeklyLossPct = (config.maxWeeklyLossPct?.times(100))?.toString() ?: ""
            maxDrawdownPct = (config.maxDrawdownPct?.times(100))?.toString() ?: ""
            overrideAccountLimits = config.overrideAccountLimits
            useMoreRestrictive = config.useMoreRestrictive
        }
    }
    fun createUpdatedConfig(): com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto =
        com.binancebot.mobile.data.remote.dto.StrategyRiskConfigDto(
            id = config?.id,
            strategyId = strategyId,
            enabled = enabled,
            maxDailyLossUsdt = maxDailyLossUsdt.toDoubleOrNull(),
            maxDailyLossPct = maxDailyLossPct.toDoubleOrNull()?.div(100),
            maxWeeklyLossUsdt = maxWeeklyLossUsdt.toDoubleOrNull(),
            maxWeeklyLossPct = maxWeeklyLossPct.toDoubleOrNull()?.div(100),
            maxDrawdownPct = maxDrawdownPct.toDoubleOrNull()?.div(100),
            overrideAccountLimits = overrideAccountLimits,
            useMoreRestrictive = useMoreRestrictive
        )
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Strategy Risk Config: ${strategyName ?: strategyId}") },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                if (errorMessage != null) {
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                        Text(text = errorMessage ?: "", modifier = Modifier.padding(Spacing.Medium), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onErrorContainer)
                    }
                }
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("Enabled")
                    Switch(checked = enabled, onCheckedChange = { enabled = it }, enabled = !isLoading)
                }
                HorizontalDivider()
                Text("Loss Limits", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                OutlinedTextField(value = maxDailyLossUsdt, onValueChange = { maxDailyLossUsdt = it }, label = { Text("Max Daily Loss (USDT)") }, modifier = Modifier.fillMaxWidth(), enabled = !isLoading && enabled)
                OutlinedTextField(value = maxDailyLossPct, onValueChange = { maxDailyLossPct = it }, label = { Text("Max Daily Loss (%)") }, modifier = Modifier.fillMaxWidth(), enabled = !isLoading && enabled)
                OutlinedTextField(value = maxWeeklyLossUsdt, onValueChange = { maxWeeklyLossUsdt = it }, label = { Text("Max Weekly Loss (USDT)") }, modifier = Modifier.fillMaxWidth(), enabled = !isLoading && enabled)
                OutlinedTextField(value = maxWeeklyLossPct, onValueChange = { maxWeeklyLossPct = it }, label = { Text("Max Weekly Loss (%)") }, modifier = Modifier.fillMaxWidth(), enabled = !isLoading && enabled)
                OutlinedTextField(value = maxDrawdownPct, onValueChange = { maxDrawdownPct = it }, label = { Text("Max Drawdown (%)") }, modifier = Modifier.fillMaxWidth(), enabled = !isLoading && enabled)
                HorizontalDivider()
                Text("Priority Mode", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("Override Account Limits")
                    Switch(checked = overrideAccountLimits, onCheckedChange = { overrideAccountLimits = it; if (it) useMoreRestrictive = false }, enabled = !isLoading && enabled)
                }
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("Use More Restrictive")
                    Switch(checked = useMoreRestrictive, onCheckedChange = { useMoreRestrictive = it; if (it) overrideAccountLimits = false }, enabled = !isLoading && enabled && !overrideAccountLimits)
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val updated = createUpdatedConfig()
                    isLoading = true
                    if (isEdit) onUpdate(updated) else onCreate(updated)
                    isLoading = false
                    onDismiss()
                },
                enabled = !isLoading
            ) { Text(if (isEdit) "Update" else "Create") }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !isLoading) { Text("Cancel") } }
    )
}

@Composable
fun MetricRow(
    label: String,
    value: String,
    valueColor: androidx.compose.ui.graphics.Color? = null,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Bold,
            color = valueColor ?: MaterialTheme.colorScheme.onSurface
        )
    }
}

internal fun formatTimestamp(timestamp: String): String {
    return try {
        val sdf = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.getDefault())
        val date = java.time.Instant.parse(timestamp).atZone(java.time.ZoneId.systemDefault()).toLocalDateTime()
        java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss").format(date)
    } catch (e: Exception) {
        timestamp
    }
}

// Enhanced EditRiskConfigDialog with all features (continuing from existing implementation)
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EditRiskConfigDialog(
    config: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?,
    isEdit: Boolean,
    isLoading: Boolean,
    errorMessage: String?,
    onDismiss: () -> Unit,
    onSave: (com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto) -> Unit,
    defaultAccountId: String? = null
) {
    // Load accounts for selection
    val accountViewModel: com.binancebot.mobile.presentation.viewmodel.AccountViewModel = androidx.hilt.navigation.compose.hiltViewModel()
    val accounts by accountViewModel.accounts.collectAsState()
    
    var selectedAccountId by remember { mutableStateOf<String?>(config?.accountId ?: defaultAccountId) }
    var showAccountDropdown by remember { mutableStateOf(false) }
    var accountError by remember { mutableStateOf<String?>(null) }
    
    // Auto-select first account if available and creating new config
    LaunchedEffect(accounts) {
        if (!isEdit && accounts.isNotEmpty() && selectedAccountId == null) {
            selectedAccountId = accounts.first().accountId
            accountError = null
        }
    }
    // State variables for all configuration fields
    var maxPortfolioExposureUsdt by remember { mutableStateOf(config?.maxPortfolioExposureUsdt?.toString() ?: "") }
    var maxPortfolioExposurePct by remember { mutableStateOf((config?.maxPortfolioExposurePct?.times(100))?.toString() ?: "") }
    var maxDailyLossUsdt by remember { mutableStateOf(config?.maxDailyLossUsdt?.toString() ?: "") }
    var maxDailyLossPct by remember { mutableStateOf((config?.maxDailyLossPct?.times(100))?.toString() ?: "") }
    var maxWeeklyLossUsdt by remember { mutableStateOf(config?.maxWeeklyLossUsdt?.toString() ?: "") }
    var maxWeeklyLossPct by remember { mutableStateOf((config?.maxWeeklyLossPct?.times(100))?.toString() ?: "") }
    var maxDrawdownPct by remember { mutableStateOf((config?.maxDrawdownPct?.times(100))?.toString() ?: "") }
    
    // Loss Reset
    var dailyLossResetTime by remember { mutableStateOf(config?.dailyLossResetTime ?: "00:00:00") }
    var weeklyLossResetDay by remember { mutableStateOf(config?.weeklyLossResetDay?.toString() ?: "1") }
    var timezone by remember { mutableStateOf(config?.timezone ?: "UTC") }
    
    // Circuit Breaker
    var circuitBreakerEnabled by remember { mutableStateOf(config?.circuitBreakerEnabled ?: false) }
    var maxConsecutiveLosses by remember { mutableStateOf(config?.maxConsecutiveLosses?.toString() ?: "") }
    var rapidLossThresholdPct by remember { mutableStateOf((config?.rapidLossThresholdPct?.times(100))?.toString() ?: "") }
    var rapidLossTimeframeMinutes by remember { mutableStateOf(config?.rapidLossTimeframeMinutes?.toString() ?: "") }
    var circuitBreakerCooldownMinutes by remember { mutableStateOf(config?.circuitBreakerCooldownMinutes?.toString() ?: "") }
    
    // Dynamic Settings
    var volatilityBasedSizingEnabled by remember { mutableStateOf(config?.volatilityBasedSizingEnabled ?: false) }
    var performanceBasedAdjustmentEnabled by remember { mutableStateOf(config?.performanceBasedAdjustmentEnabled ?: false) }
    var kellyCriterionEnabled by remember { mutableStateOf(config?.kellyCriterionEnabled ?: false) }
    var kellyFraction by remember { mutableStateOf((config?.kellyFraction?.times(100))?.toString() ?: "25") }
    
    // Correlation Limits
    var correlationLimitsEnabled by remember { mutableStateOf(config?.correlationLimitsEnabled ?: false) }
    var maxCorrelationExposurePct by remember { mutableStateOf((config?.maxCorrelationExposurePct?.times(100))?.toString() ?: "") }
    
    // Margin Protection
    var marginCallProtectionEnabled by remember { mutableStateOf(config?.marginCallProtectionEnabled ?: true) }
    var minMarginRatio by remember { mutableStateOf((config?.minMarginRatio?.times(100))?.toString() ?: "") }
    
    // Trade Frequency
    var maxTradesPerDayPerStrategy by remember { mutableStateOf(config?.maxTradesPerDayPerStrategy?.toString() ?: "") }
    var maxTradesPerDayTotal by remember { mutableStateOf(config?.maxTradesPerDayTotal?.toString() ?: "") }
    
    // Order Size
    var autoReduceOrderSize by remember { mutableStateOf(config?.autoReduceOrderSize ?: false) }
    
    fun createUpdatedConfig(): com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto {
        // Use selected account ID, fallback to config's account ID
        val finalAccountId = selectedAccountId ?: config?.accountId
        
        return com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto(
            id = config?.id,
            accountId = finalAccountId,
            maxPortfolioExposureUsdt = maxPortfolioExposureUsdt.toDoubleOrNull(),
            maxPortfolioExposurePct = maxPortfolioExposurePct.toDoubleOrNull()?.div(100),
            maxDailyLossUsdt = maxDailyLossUsdt.toDoubleOrNull(),
            maxDailyLossPct = maxDailyLossPct.toDoubleOrNull()?.div(100),
            maxWeeklyLossUsdt = maxWeeklyLossUsdt.toDoubleOrNull(),
            maxWeeklyLossPct = maxWeeklyLossPct.toDoubleOrNull()?.div(100),
            maxDrawdownPct = maxDrawdownPct.toDoubleOrNull()?.div(100),
            dailyLossResetTime = dailyLossResetTime,
            weeklyLossResetDay = weeklyLossResetDay.toIntOrNull() ?: 1, // Default to Monday
            timezone = timezone,
            circuitBreakerEnabled = circuitBreakerEnabled,
            // Only set circuit breaker fields if enabled
            maxConsecutiveLosses = if (circuitBreakerEnabled) maxConsecutiveLosses.toIntOrNull() else null,
            rapidLossThresholdPct = if (circuitBreakerEnabled) rapidLossThresholdPct.toDoubleOrNull()?.div(100) else null,
            rapidLossTimeframeMinutes = if (circuitBreakerEnabled) rapidLossTimeframeMinutes.toIntOrNull() else null,
            circuitBreakerCooldownMinutes = if (circuitBreakerEnabled) circuitBreakerCooldownMinutes.toIntOrNull() else null,
            volatilityBasedSizingEnabled = volatilityBasedSizingEnabled,
            performanceBasedAdjustmentEnabled = performanceBasedAdjustmentEnabled,
            kellyCriterionEnabled = kellyCriterionEnabled,
            kellyFraction = if (kellyCriterionEnabled) kellyFraction.toDoubleOrNull()?.div(100) else null,
            correlationLimitsEnabled = correlationLimitsEnabled,
            maxCorrelationExposurePct = if (correlationLimitsEnabled) maxCorrelationExposurePct.toDoubleOrNull()?.div(100) else null,
            marginCallProtectionEnabled = marginCallProtectionEnabled,
            minMarginRatio = if (marginCallProtectionEnabled) minMarginRatio.toDoubleOrNull()?.div(100) else null,
            maxTradesPerDayPerStrategy = maxTradesPerDayPerStrategy.toIntOrNull(),
            maxTradesPerDayTotal = maxTradesPerDayTotal.toIntOrNull(),
            autoReduceOrderSize = autoReduceOrderSize
        )
    }
    
    AlertDialog(
        onDismissRequest = { if (!isLoading) onDismiss() },
        title = { Text(if (isEdit) "Edit Risk Configuration" else "Create Risk Configuration") },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                if (errorMessage != null) {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        )
                    ) {
                        Text(
                            text = errorMessage,
                            modifier = Modifier.padding(Spacing.Medium),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                    }
                }
                
                // Account Selection (required for new configs)
                if (!isEdit) {
                    Text(
                        text = "Account Selection *",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold
                    )
                    if (accounts.isEmpty()) {
                        Text(
                            text = "Loading accounts...",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    } else {
                        ExposedDropdownMenuBox(
                            expanded = showAccountDropdown,
                            onExpandedChange = { showAccountDropdown = !showAccountDropdown }
                        ) {
                            OutlinedTextField(
                                value = accounts.find { it.accountId == selectedAccountId }?.let { account ->
                                    "${account.name ?: account.accountId}${if (account.testnet) " (Testnet)" else ""}"
                                } ?: "Select Account",
                                onValueChange = {},
                                readOnly = true,
                                label = { Text("Account *") },
                                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = showAccountDropdown) },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .menuAnchor(),
                                singleLine = true,
                                isError = selectedAccountId == null || accountError != null,
                                supportingText = accountError?.let { { Text(it) } },
                                enabled = !isLoading
                            )
                            ExposedDropdownMenu(
                                expanded = showAccountDropdown,
                                onDismissRequest = { showAccountDropdown = false }
                            ) {
                                accounts.forEach { account ->
                                    DropdownMenuItem(
                                        text = { 
                                            Text("${account.name ?: account.accountId}${if (account.testnet) " (Testnet)" else ""}")
                                        },
                                        onClick = {
                                            selectedAccountId = account.accountId
                                            showAccountDropdown = false
                                        }
                                    )
                                }
                            }
                        }
                    }
                    HorizontalDivider()
                }
                
                // Portfolio Limits Section
                Text(
                    text = "Portfolio Limits",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                OutlinedTextField(
                    value = maxPortfolioExposureUsdt,
                    onValueChange = { maxPortfolioExposureUsdt = it },
                    label = { Text("Max Portfolio Exposure (USDT)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = maxPortfolioExposurePct,
                    onValueChange = { maxPortfolioExposurePct = it },
                    label = { Text("Max Portfolio Exposure (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = maxDailyLossUsdt,
                    onValueChange = { maxDailyLossUsdt = it },
                    label = { Text("Max Daily Loss (USDT)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = maxDailyLossPct,
                    onValueChange = { maxDailyLossPct = it },
                    label = { Text("Max Daily Loss (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = maxWeeklyLossUsdt,
                    onValueChange = { maxWeeklyLossUsdt = it },
                    label = { Text("Max Weekly Loss (USDT)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = maxWeeklyLossPct,
                    onValueChange = { maxWeeklyLossPct = it },
                    label = { Text("Max Weekly Loss (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = maxDrawdownPct,
                    onValueChange = { maxDrawdownPct = it },
                    label = { Text("Max Drawdown (%)") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                
                HorizontalDivider()
                
                // Circuit Breaker Section
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Circuit Breaker Enabled")
                    Switch(
                        checked = circuitBreakerEnabled,
                        onCheckedChange = { circuitBreakerEnabled = it },
                        enabled = !isLoading
                    )
                }
                
                if (circuitBreakerEnabled) {
                    OutlinedTextField(
                        value = maxConsecutiveLosses,
                        onValueChange = { maxConsecutiveLosses = it },
                        label = { Text("Max Consecutive Losses") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                    OutlinedTextField(
                        value = rapidLossThresholdPct,
                        onValueChange = { rapidLossThresholdPct = it },
                        label = { Text("Rapid Loss Threshold (%)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                    OutlinedTextField(
                        value = rapidLossTimeframeMinutes,
                        onValueChange = { rapidLossTimeframeMinutes = it },
                        label = { Text("Rapid Loss Timeframe (minutes)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                    OutlinedTextField(
                        value = circuitBreakerCooldownMinutes,
                        onValueChange = { circuitBreakerCooldownMinutes = it },
                        label = { Text("Circuit Breaker Cooldown (minutes)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                }
                
                HorizontalDivider()
                
                // Advanced Settings
                Text(
                    text = "Advanced Settings",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Volatility-Based Sizing")
                    Switch(
                        checked = volatilityBasedSizingEnabled,
                        onCheckedChange = { volatilityBasedSizingEnabled = it },
                        enabled = !isLoading
                    )
                }
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Performance-Based Adjustment")
                    Switch(
                        checked = performanceBasedAdjustmentEnabled,
                        onCheckedChange = { performanceBasedAdjustmentEnabled = it },
                        enabled = !isLoading
                    )
                }
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Kelly Criterion")
                    Switch(
                        checked = kellyCriterionEnabled,
                        onCheckedChange = { kellyCriterionEnabled = it },
                        enabled = !isLoading
                    )
                }
                
                if (kellyCriterionEnabled) {
                    OutlinedTextField(
                        value = kellyFraction,
                        onValueChange = { kellyFraction = it },
                        label = { Text("Kelly Fraction (%)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                }
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Correlation Limits")
                    Switch(
                        checked = correlationLimitsEnabled,
                        onCheckedChange = { correlationLimitsEnabled = it },
                        enabled = !isLoading
                    )
                }
                
                if (correlationLimitsEnabled) {
                    OutlinedTextField(
                        value = maxCorrelationExposurePct,
                        onValueChange = { maxCorrelationExposurePct = it },
                        label = { Text("Max Correlation Exposure (%)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                }
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Margin Call Protection")
                    Switch(
                        checked = marginCallProtectionEnabled,
                        onCheckedChange = { marginCallProtectionEnabled = it },
                        enabled = !isLoading
                    )
                }
                
                if (marginCallProtectionEnabled) {
                    OutlinedTextField(
                        value = minMarginRatio,
                        onValueChange = { minMarginRatio = it },
                        label = { Text("Min Margin Ratio (%)") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isLoading
                    )
                }
                
                OutlinedTextField(
                    value = maxTradesPerDayPerStrategy,
                    onValueChange = { maxTradesPerDayPerStrategy = it },
                    label = { Text("Max Trades/Day Per Strategy") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                
                OutlinedTextField(
                    value = maxTradesPerDayTotal,
                    onValueChange = { maxTradesPerDayTotal = it },
                    label = { Text("Max Trades/Day Total") },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading
                )
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Auto-Reduce Order Size")
                    Switch(
                        checked = autoReduceOrderSize,
                        onCheckedChange = { autoReduceOrderSize = it },
                        enabled = !isLoading
                    )
                }
                
                if (isLoading) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Center
                    ) {
                        CircularProgressIndicator(modifier = Modifier.padding(Spacing.Medium))
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { 
                    if (!isEdit) {
                        if (selectedAccountId == null) {
                            accountError = "Account selection is required"
                            return@TextButton
                        }
                        accountError = null
                    }
                    onSave(createUpdatedConfig()) 
                },
                enabled = !isLoading && (isEdit || selectedAccountId != null)
            ) {
                Text("Save")
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isLoading
            ) {
                Text("Cancel")
            }
        }
    )
}

