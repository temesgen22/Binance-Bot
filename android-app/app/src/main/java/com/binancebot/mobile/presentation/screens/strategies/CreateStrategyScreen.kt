package com.binancebot.mobile.presentation.screens.strategies

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.domain.model.Account
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.viewmodel.AccountViewModel
import com.binancebot.mobile.presentation.viewmodel.StrategiesViewModel
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto
import kotlinx.coroutines.flow.MutableStateFlow

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CreateStrategyScreen(
    navController: NavController,
    strategiesViewModel: StrategiesViewModel = hiltViewModel(),
    accountViewModel: AccountViewModel = hiltViewModel()
) {
    var name by remember { mutableStateOf("") }
    var symbol by remember { mutableStateOf("") }
    var strategyType by remember { mutableStateOf("scalping") }
    var leverage by remember { mutableStateOf("5") }
    var riskPerTrade by remember { mutableStateOf("0.01") }
    var fixedAmount by remember { mutableStateOf("") }
    var selectedAccountId by remember { mutableStateOf<String?>(null) }
    var showAccountDropdown by remember { mutableStateOf(false) }
    var isCopyMode by remember { mutableStateOf(false) }
    
    // Strategy parameters - initialized with defaults based on strategy type
    // Scalping/Reverse Scalping parameters
    var emaFast by remember { mutableStateOf("8") }
    var emaSlow by remember { mutableStateOf("21") }
    var takeProfitPct by remember { mutableStateOf("0.004") }
    var stopLossPct by remember { mutableStateOf("0.002") }
    var intervalSeconds by remember { mutableStateOf("10") }
    var klineInterval by remember { mutableStateOf("1m") }
    var enableShort by remember { mutableStateOf(true) }
    var minEmaSeparation by remember { mutableStateOf("0.0002") }
    var enableHtfBias by remember { mutableStateOf(true) }
    var cooldownCandles by remember { mutableStateOf("2") }
    var trailingStopEnabled by remember { mutableStateOf(false) }
    var trailingStopActivationPct by remember { mutableStateOf("0.0") }
    var enableEmaCrossExit by remember { mutableStateOf(true) }
    
    // Range Mean Reversion parameters
    var lookbackPeriod by remember { mutableStateOf("150") }
    var buyZonePct by remember { mutableStateOf("0.2") }
    var sellZonePct by remember { mutableStateOf("0.2") }
    var emaFastPeriod by remember { mutableStateOf("20") }
    var emaSlowPeriod by remember { mutableStateOf("50") }
    var maxEmaSpreadPct by remember { mutableStateOf("0.005") }
    var maxAtrMultiplier by remember { mutableStateOf("2.0") }
    var rsiPeriod by remember { mutableStateOf("14") }
    var rsiOversold by remember { mutableStateOf("40.0") }
    var rsiOverbought by remember { mutableStateOf("60.0") }
    var tpBufferPct by remember { mutableStateOf("0.001") }
    var slBufferPct by remember { mutableStateOf("0.002") }
    
    // Initialize defaults when strategy type changes
    LaunchedEffect(strategyType) {
        when (strategyType) {
            "scalping", "reverse_scalping" -> {
                // Use current values or defaults
                if (emaFast.isEmpty()) emaFast = "8"
                if (emaSlow.isEmpty()) emaSlow = "21"
                if (takeProfitPct.isEmpty()) takeProfitPct = "0.004"
                if (stopLossPct.isEmpty()) stopLossPct = "0.002"
                if (intervalSeconds.isEmpty()) intervalSeconds = "10"
                if (klineInterval.isEmpty()) klineInterval = "1m"
                if (minEmaSeparation.isEmpty()) minEmaSeparation = "0.0002"
                if (cooldownCandles.isEmpty()) cooldownCandles = "2"
                if (trailingStopActivationPct.isEmpty()) trailingStopActivationPct = "0.0"
            }
            "range_mean_reversion" -> {
                // Use current values or defaults
                if (lookbackPeriod.isEmpty()) lookbackPeriod = "150"
                if (buyZonePct.isEmpty()) buyZonePct = "0.2"
                if (sellZonePct.isEmpty()) sellZonePct = "0.2"
                if (emaFastPeriod.isEmpty()) emaFastPeriod = "20"
                if (emaSlowPeriod.isEmpty()) emaSlowPeriod = "50"
                if (maxEmaSpreadPct.isEmpty()) maxEmaSpreadPct = "0.005"
                if (maxAtrMultiplier.isEmpty()) maxAtrMultiplier = "2.0"
                if (rsiPeriod.isEmpty()) rsiPeriod = "14"
                if (rsiOversold.isEmpty()) rsiOversold = "40.0"
                if (rsiOverbought.isEmpty()) rsiOverbought = "60.0"
                if (tpBufferPct.isEmpty()) tpBufferPct = "0.001"
                if (slBufferPct.isEmpty()) slBufferPct = "0.002"
                if (klineInterval.isEmpty()) klineInterval = "5m"
            }
        }
    }
    
    val accounts by accountViewModel.accounts.collectAsState()
    val uiState by strategiesViewModel.uiState.collectAsState()
    
    // Auto-select first account if available
    LaunchedEffect(accounts) {
        if (accounts.isNotEmpty() && selectedAccountId == null) {
            selectedAccountId = accounts.first().accountId
        }
    }
    
    val snackbarHostState = remember { SnackbarHostState() }
    
    // Parent ViewModels (if strategies is in back stack - e.g. navigated from Copy)
    val strategiesBackEntry = remember(navController) { navController.getBackStackEntry(Screen.Strategies.route) }
    val parentStrategiesViewModel: StrategiesViewModel? = strategiesBackEntry?.let { hiltViewModel(it) }
    val performanceViewModel: com.binancebot.mobile.presentation.viewmodel.StrategyPerformanceViewModel? =
        strategiesBackEntry?.let { hiltViewModel(it) }
    val strategyToCopyFlow = parentStrategiesViewModel?.strategyToCopy
        ?: remember { MutableStateFlow<StrategyPerformanceDto?>(null) }
    val strategyToCopy by strategyToCopyFlow.collectAsState()
    
    // Pre-fill form when copying from existing strategy
    LaunchedEffect(strategyToCopy) {
        strategyToCopy?.let { perf ->
            name = "Copy of ${perf.strategyName}"
            symbol = perf.symbol
            strategyType = perf.strategyType
            leverage = perf.leverage.toString()
            riskPerTrade = String.format("%.4f", perf.riskPerTrade)
            fixedAmount = perf.fixedAmount?.toString() ?: ""
            selectedAccountId = perf.accountId
            klineInterval = (perf.params["kline_interval"] as? String) ?: when (perf.strategyType) {
                "range_mean_reversion" -> "5m"
                else -> "1m"
            }
            enableShort = (perf.params["enable_short"] as? Boolean) ?: true
            cooldownCandles = (perf.params["cooldown_candles"] as? Number)?.toString() ?: "2"
            when (perf.strategyType) {
                "scalping", "reverse_scalping" -> {
                    emaFast = (perf.params["ema_fast"] as? Number)?.toString() ?: "8"
                    emaSlow = (perf.params["ema_slow"] as? Number)?.toString() ?: "21"
                    takeProfitPct = (perf.params["take_profit_pct"] as? Number)?.toString() ?: "0.004"
                    stopLossPct = (perf.params["stop_loss_pct"] as? Number)?.toString() ?: "0.002"
                    intervalSeconds = (perf.params["interval_seconds"] as? Number)?.toString() ?: "10"
                    minEmaSeparation = (perf.params["min_ema_separation"] as? Number)?.toString() ?: "0.0002"
                    enableHtfBias = (perf.params["enable_htf_bias"] as? Boolean) ?: true
                    trailingStopEnabled = (perf.params["trailing_stop_enabled"] as? Boolean) ?: false
                    trailingStopActivationPct = (perf.params["trailing_stop_activation_pct"] as? Number)?.toString() ?: "0.0"
                    enableEmaCrossExit = (perf.params["enable_ema_cross_exit"] as? Boolean) ?: true
                }
                "range_mean_reversion" -> {
                    lookbackPeriod = (perf.params["lookback_period"] as? Number)?.toString() ?: "150"
                    buyZonePct = (perf.params["buy_zone_pct"] as? Number)?.toString() ?: "0.2"
                    sellZonePct = (perf.params["sell_zone_pct"] as? Number)?.toString() ?: "0.2"
                    emaFastPeriod = (perf.params["ema_fast_period"] as? Number)?.toString() ?: "20"
                    emaSlowPeriod = (perf.params["ema_slow_period"] as? Number)?.toString() ?: "50"
                    maxEmaSpreadPct = (perf.params["max_ema_spread_pct"] as? Number)?.toString() ?: "0.005"
                    maxAtrMultiplier = (perf.params["max_atr_multiplier"] as? Number)?.toString() ?: "2.0"
                    rsiPeriod = (perf.params["rsi_period"] as? Number)?.toString() ?: "14"
                    rsiOversold = (perf.params["rsi_oversold"] as? Number)?.toString() ?: "40.0"
                    rsiOverbought = (perf.params["rsi_overbought"] as? Number)?.toString() ?: "60.0"
                    tpBufferPct = (perf.params["tp_buffer_pct"] as? Number)?.toString() ?: "0.001"
                    slBufferPct = (perf.params["sl_buffer_pct"] as? Number)?.toString() ?: "0.002"
                }
                else -> {}
            }
            isCopyMode = true
            parentStrategiesViewModel?.clearStrategyToCopy()
        }
    }
    
    // Show success Snackbar and navigate back on create success
    LaunchedEffect(uiState) {
        if (uiState is com.binancebot.mobile.presentation.viewmodel.StrategiesUiState.CreateSuccess) {
            snackbarHostState.showSnackbar(
                message = "Strategy created successfully",
                duration = SnackbarDuration.Short
            )
            kotlinx.coroutines.delay(1500)
            performanceViewModel?.loadPerformance()
            strategiesViewModel.clearCreateSuccess()
            navController.popBackStack()
        }
    }
    
    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = {
            TopAppBar(
                title = { Text(if (isCopyMode) "Copy Strategy" else "Create Strategy") },
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
            // Strategy Name
            OutlinedTextField(
                value = name,
                onValueChange = { name = it },
                label = { Text("Strategy Name *") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                isError = name.isBlank()
            )
            
            // Symbol
            OutlinedTextField(
                value = symbol,
                onValueChange = { symbol = it.uppercase() },
                label = { Text("Symbol (e.g., BTCUSDT) *") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                isError = symbol.isBlank()
            )
            
            // Strategy Type
            var showStrategyTypeDropdown by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(
                expanded = showStrategyTypeDropdown,
                onExpandedChange = { showStrategyTypeDropdown = !showStrategyTypeDropdown }
            ) {
                OutlinedTextField(
                    value = strategyType.replace("_", " ").replaceFirstChar { it.uppercase() },
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Strategy Type *") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = showStrategyTypeDropdown) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor(),
                    singleLine = true
                )
                ExposedDropdownMenu(
                    expanded = showStrategyTypeDropdown,
                    onDismissRequest = { showStrategyTypeDropdown = false }
                ) {
                    listOf("scalping", "reverse_scalping", "range_mean_reversion").forEach { type ->
                        DropdownMenuItem(
                            text = { Text(type.replace("_", " ").replaceFirstChar { it.uppercase() }) },
                            onClick = {
                                strategyType = type
                                showStrategyTypeDropdown = false
                                // Reset parameters to defaults when type changes
                                when (type) {
                                    "scalping", "reverse_scalping" -> {
                                        emaFast = "8"
                                        emaSlow = "21"
                                        takeProfitPct = "0.004"
                                        stopLossPct = "0.002"
                                        intervalSeconds = "10"
                                        klineInterval = "1m"
                                        enableShort = true
                                        minEmaSeparation = "0.0002"
                                        enableHtfBias = true
                                        cooldownCandles = "2"
                                        trailingStopEnabled = false
                                        trailingStopActivationPct = "0.0"
                                        enableEmaCrossExit = true
                                    }
                                    "range_mean_reversion" -> {
                                        lookbackPeriod = "150"
                                        buyZonePct = "0.2"
                                        sellZonePct = "0.2"
                                        emaFastPeriod = "20"
                                        emaSlowPeriod = "50"
                                        maxEmaSpreadPct = "0.005"
                                        maxAtrMultiplier = "2.0"
                                        rsiPeriod = "14"
                                        rsiOversold = "40.0"
                                        rsiOverbought = "60.0"
                                        tpBufferPct = "0.001"
                                        slBufferPct = "0.002"
                                        klineInterval = "5m"
                                        enableShort = true
                                        cooldownCandles = "2"
                                    }
                                }
                            }
                        )
                    }
                }
            }
            
            // Account Selection
            if (accounts.isNotEmpty()) {
                ExposedDropdownMenuBox(
                    expanded = showAccountDropdown,
                    onExpandedChange = { showAccountDropdown = !showAccountDropdown }
                ) {
                    OutlinedTextField(
                        value = accounts.find { it.accountId == selectedAccountId }?.name
                            ?: accounts.find { it.accountId == selectedAccountId }?.accountId
                            ?: "Select Account",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Account *") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = showAccountDropdown) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        singleLine = true
                    )
                    ExposedDropdownMenu(
                        expanded = showAccountDropdown,
                        onDismissRequest = { showAccountDropdown = false }
                    ) {
                        accounts.forEach { account ->
                            DropdownMenuItem(
                                text = { Text("${account.name ?: account.accountId} (${account.accountId})") },
                                onClick = {
                                    selectedAccountId = account.accountId
                                    showAccountDropdown = false
                                }
                            )
                        }
                    }
                }
            }
            
            // Leverage
            OutlinedTextField(
                value = leverage,
                onValueChange = { if (it.all { char -> char.isDigit() }) leverage = it },
                label = { Text("Leverage (1-50) *") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                isError = leverage.toIntOrNull()?.let { it !in 1..50 } ?: true
            )
            
            // Risk Per Trade
            OutlinedTextField(
                value = riskPerTrade,
                onValueChange = { riskPerTrade = it },
                label = { Text("Risk Per Trade (0.01 = 1%)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                supportingText = { Text("Leave empty if using fixed amount") }
            )
            
            // Fixed Amount
            OutlinedTextField(
                value = fixedAmount,
                onValueChange = { fixedAmount = it },
                label = { Text("Fixed Amount (USDT)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                supportingText = { Text("Optional: Overrides risk per trade if set") }
            )
            
            // Strategy Parameters Section
            HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
            Text(
                text = "Strategy Parameters",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(vertical = Spacing.Small)
            )
            
            // Show parameters based on strategy type
            when (strategyType) {
                "scalping", "reverse_scalping" -> {
                    // EMA Scalping Parameters
                    OutlinedTextField(
                        value = emaFast,
                        onValueChange = { if (it.all { char -> char.isDigit() }) emaFast = it },
                        label = { Text("EMA Fast Period") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = emaSlow,
                        onValueChange = { if (it.all { char -> char.isDigit() }) emaSlow = it },
                        label = { Text("EMA Slow Period") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = takeProfitPct,
                        onValueChange = { takeProfitPct = it },
                        label = { Text("Take Profit % (e.g., 0.004 = 0.4%)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = stopLossPct,
                        onValueChange = { stopLossPct = it },
                        label = { Text("Stop Loss % (e.g., 0.002 = 0.2%)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = intervalSeconds,
                        onValueChange = { if (it.all { char -> char.isDigit() }) intervalSeconds = it },
                        label = { Text("Interval Seconds") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = klineInterval,
                        onValueChange = { klineInterval = it },
                        label = { Text("Kline Interval (1m, 5m, 15m, etc.)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = enableShort,
                            onCheckedChange = { enableShort = it }
                        )
                        Text("Enable Short Trading", modifier = Modifier.padding(start = Spacing.Small))
                    }
                    OutlinedTextField(
                        value = minEmaSeparation,
                        onValueChange = { minEmaSeparation = it },
                        label = { Text("Min EMA Separation (0.0002 = 0.02%)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = enableHtfBias,
                            onCheckedChange = { enableHtfBias = it }
                        )
                        Text("Enable HTF Bias", modifier = Modifier.padding(start = Spacing.Small))
                    }
                    OutlinedTextField(
                        value = cooldownCandles,
                        onValueChange = { if (it.all { char -> char.isDigit() }) cooldownCandles = it },
                        label = { Text("Cooldown Candles") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = trailingStopEnabled,
                            onCheckedChange = { trailingStopEnabled = it }
                        )
                        Text("Trailing Stop Enabled", modifier = Modifier.padding(start = Spacing.Small))
                    }
                    if (trailingStopEnabled) {
                        OutlinedTextField(
                            value = trailingStopActivationPct,
                            onValueChange = { trailingStopActivationPct = it },
                            label = { Text("Trailing Stop Activation %") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = enableEmaCrossExit,
                            onCheckedChange = { enableEmaCrossExit = it }
                        )
                        Text("Enable EMA Cross Exit", modifier = Modifier.padding(start = Spacing.Small))
                    }
                }
                "range_mean_reversion" -> {
                    // Range Mean Reversion Parameters
                    OutlinedTextField(
                        value = lookbackPeriod,
                        onValueChange = { if (it.all { char -> char.isDigit() }) lookbackPeriod = it },
                        label = { Text("Lookback Period (candles)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = buyZonePct,
                        onValueChange = { buyZonePct = it },
                        label = { Text("Buy Zone % (0.2 = bottom 20%)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = sellZonePct,
                        onValueChange = { sellZonePct = it },
                        label = { Text("Sell Zone % (0.2 = top 20%)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = emaFastPeriod,
                        onValueChange = { if (it.all { char -> char.isDigit() }) emaFastPeriod = it },
                        label = { Text("EMA Fast Period") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = emaSlowPeriod,
                        onValueChange = { if (it.all { char -> char.isDigit() }) emaSlowPeriod = it },
                        label = { Text("EMA Slow Period") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = maxEmaSpreadPct,
                        onValueChange = { maxEmaSpreadPct = it },
                        label = { Text("Max EMA Spread %") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = maxAtrMultiplier,
                        onValueChange = { maxAtrMultiplier = it },
                        label = { Text("Max ATR Multiplier") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = rsiPeriod,
                        onValueChange = { if (it.all { char -> char.isDigit() }) rsiPeriod = it },
                        label = { Text("RSI Period") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = rsiOversold,
                        onValueChange = { rsiOversold = it },
                        label = { Text("RSI Oversold Threshold") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = rsiOverbought,
                        onValueChange = { rsiOverbought = it },
                        label = { Text("RSI Overbought Threshold") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = klineInterval,
                        onValueChange = { klineInterval = it },
                        label = { Text("Kline Interval (1m, 5m, 15m, etc.)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = tpBufferPct,
                        onValueChange = { tpBufferPct = it },
                        label = { Text("TP Buffer %") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = slBufferPct,
                        onValueChange = { slBufferPct = it },
                        label = { Text("SL Buffer %") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = enableShort,
                            onCheckedChange = { enableShort = it }
                        )
                        Text("Enable Short Trading", modifier = Modifier.padding(start = Spacing.Small))
                    }
                    OutlinedTextField(
                        value = cooldownCandles,
                        onValueChange = { if (it.all { char -> char.isDigit() }) cooldownCandles = it },
                        label = { Text("Cooldown Candles") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                }
            }
            
            // Error Message
            if (uiState is com.binancebot.mobile.presentation.viewmodel.StrategiesUiState.Error) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Text(
                        text = (uiState as com.binancebot.mobile.presentation.viewmodel.StrategiesUiState.Error).message,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        modifier = Modifier.padding(Spacing.Medium),
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }
            
            Spacer(modifier = Modifier.height(Spacing.Medium))
            
            // Create Button
            val isLoading = uiState is com.binancebot.mobile.presentation.viewmodel.StrategiesUiState.Loading ||
                    uiState is com.binancebot.mobile.presentation.viewmodel.StrategiesUiState.CreateSuccess
            val isValid = name.isNotBlank() &&
                    symbol.isNotBlank() &&
                    leverage.toIntOrNull()?.let { it in 1..50 } == true &&
                    selectedAccountId != null &&
                    (riskPerTrade.toDoubleOrNull() != null || fixedAmount.toDoubleOrNull() != null) &&
                    !isLoading
            
            Button(
                onClick = {
                    selectedAccountId?.let { accountId ->
                        // Build params map based on strategy type
                        val params = buildParamsMap(
                            strategyType = strategyType,
                            emaFast = emaFast,
                            emaSlow = emaSlow,
                            takeProfitPct = takeProfitPct,
                            stopLossPct = stopLossPct,
                            intervalSeconds = intervalSeconds,
                            klineInterval = klineInterval,
                            enableShort = enableShort,
                            minEmaSeparation = minEmaSeparation,
                            enableHtfBias = enableHtfBias,
                            cooldownCandles = cooldownCandles,
                            trailingStopEnabled = trailingStopEnabled,
                            trailingStopActivationPct = trailingStopActivationPct,
                            enableEmaCrossExit = enableEmaCrossExit,
                            lookbackPeriod = lookbackPeriod,
                            buyZonePct = buyZonePct,
                            sellZonePct = sellZonePct,
                            emaFastPeriod = emaFastPeriod,
                            emaSlowPeriod = emaSlowPeriod,
                            maxEmaSpreadPct = maxEmaSpreadPct,
                            maxAtrMultiplier = maxAtrMultiplier,
                            rsiPeriod = rsiPeriod,
                            rsiOversold = rsiOversold,
                            rsiOverbought = rsiOverbought,
                            tpBufferPct = tpBufferPct,
                            slBufferPct = slBufferPct
                        )
                        strategiesViewModel.createStrategy(
                            name = name.trim(),
                            symbol = symbol.trim().uppercase(),
                            strategyType = strategyType,
                            leverage = leverage.toInt(),
                            riskPerTrade = riskPerTrade.toDoubleOrNull(),
                            fixedAmount = fixedAmount.toDoubleOrNull(),
                            accountId = accountId,
                            params = params
                        )
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = isValid
            ) {
                if (isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        color = MaterialTheme.colorScheme.onPrimary
                    )
                    Spacer(modifier = Modifier.width(Spacing.Small))
                }
                Text(if (uiState is com.binancebot.mobile.presentation.viewmodel.StrategiesUiState.CreateSuccess) "Success!" else "Create Strategy")
            }
        }
    }
}

// Helper function to build params map based on strategy type
fun buildParamsMap(
    strategyType: String,
    // Scalping/Reverse Scalping params
    emaFast: String = "8",
    emaSlow: String = "21",
    takeProfitPct: String = "0.004",
    stopLossPct: String = "0.002",
    intervalSeconds: String = "10",
    klineInterval: String = "1m",
    enableShort: Boolean = true,
    minEmaSeparation: String = "0.0002",
    enableHtfBias: Boolean = true,
    cooldownCandles: String = "2",
    trailingStopEnabled: Boolean = false,
    trailingStopActivationPct: String = "0.0",
    enableEmaCrossExit: Boolean = true,
    // Range Mean Reversion params
    lookbackPeriod: String = "150",
    buyZonePct: String = "0.2",
    sellZonePct: String = "0.2",
    emaFastPeriod: String = "20",
    emaSlowPeriod: String = "50",
    maxEmaSpreadPct: String = "0.005",
    maxAtrMultiplier: String = "2.0",
    rsiPeriod: String = "14",
    rsiOversold: String = "40.0",
    rsiOverbought: String = "60.0",
    tpBufferPct: String = "0.001",
    slBufferPct: String = "0.002"
): Map<String, Any> {
    return when (strategyType) {
        "scalping", "reverse_scalping" -> {
            mapOf<String, Any>(
                "ema_fast" to (emaFast.toIntOrNull() ?: 8),
                "ema_slow" to (emaSlow.toIntOrNull() ?: 21),
                "take_profit_pct" to (takeProfitPct.toDoubleOrNull() ?: 0.004),
                "stop_loss_pct" to (stopLossPct.toDoubleOrNull() ?: 0.002),
                "interval_seconds" to (intervalSeconds.toIntOrNull() ?: 10),
                "kline_interval" to klineInterval,
                "enable_short" to enableShort,
                "min_ema_separation" to (minEmaSeparation.toDoubleOrNull() ?: 0.0002),
                "enable_htf_bias" to enableHtfBias,
                "cooldown_candles" to (cooldownCandles.toIntOrNull() ?: 2),
                "trailing_stop_enabled" to trailingStopEnabled,
                "trailing_stop_activation_pct" to (trailingStopActivationPct.toDoubleOrNull() ?: 0.0),
                "enable_ema_cross_exit" to enableEmaCrossExit
            )
        }
        "range_mean_reversion" -> {
            mapOf<String, Any>(
                "lookback_period" to (lookbackPeriod.toIntOrNull() ?: 150),
                "buy_zone_pct" to (buyZonePct.toDoubleOrNull() ?: 0.2),
                "sell_zone_pct" to (sellZonePct.toDoubleOrNull() ?: 0.2),
                "ema_fast_period" to (emaFastPeriod.toIntOrNull() ?: 20),
                "ema_slow_period" to (emaSlowPeriod.toIntOrNull() ?: 50),
                "max_ema_spread_pct" to (maxEmaSpreadPct.toDoubleOrNull() ?: 0.005),
                "max_atr_multiplier" to (maxAtrMultiplier.toDoubleOrNull() ?: 2.0),
                "rsi_period" to (rsiPeriod.toIntOrNull() ?: 14),
                "rsi_oversold" to (rsiOversold.toDoubleOrNull() ?: 40.0),
                "rsi_overbought" to (rsiOverbought.toDoubleOrNull() ?: 60.0),
                "tp_buffer_pct" to (tpBufferPct.toDoubleOrNull() ?: 0.001),
                "sl_buffer_pct" to (slBufferPct.toDoubleOrNull() ?: 0.002),
                "kline_interval" to klineInterval,
                "enable_short" to enableShort,
                "cooldown_candles" to (cooldownCandles.toIntOrNull() ?: 2)
            )
        }
        else -> emptyMap()
    }
}

