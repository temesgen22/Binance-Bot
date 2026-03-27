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
    var pnlGivebackEnabled by remember { mutableStateOf(false) }
    var pnlGivebackFromPeakUsdt by remember { mutableStateOf("5.0") }
    var pnlGivebackMinPeakUsdt by remember { mutableStateOf("0.0") }
    var enableEmaCrossExit by remember { mutableStateOf(true) }
    var useRsiFilter by remember { mutableStateOf(false) }
    var rsiPeriodFilter by remember { mutableStateOf("14") }
    var rsiLongMin by remember { mutableStateOf("50.0") }
    var rsiShortMax by remember { mutableStateOf("50.0") }
    var useAtrFilter by remember { mutableStateOf(false) }
    var atrPeriod by remember { mutableStateOf("14") }
    var atrMinPct by remember { mutableStateOf("0.0") }
    var atrMaxPct by remember { mutableStateOf("100.0") }
    var useVolumeFilter by remember { mutableStateOf(false) }
    var volumeMaPeriod by remember { mutableStateOf("20") }
    var volumeMultiplierMin by remember { mutableStateOf("1.0") }
    var useStructureFilter by remember { mutableStateOf(false) }
    var structureLeftBars by remember { mutableStateOf("2") }
    var structureRightBars by remember { mutableStateOf("2") }
    var structureConfirmOnClose by remember { mutableStateOf(true) }
    
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
    var slTriggerMode by remember { mutableStateOf("live_price") }
    
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
                if (pnlGivebackFromPeakUsdt.isEmpty()) pnlGivebackFromPeakUsdt = "5.0"
                if (pnlGivebackMinPeakUsdt.isEmpty()) pnlGivebackMinPeakUsdt = "0.0"
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
                    pnlGivebackEnabled = (perf.params["pnl_giveback_enabled"] as? Boolean) ?: false
                    pnlGivebackFromPeakUsdt = (perf.params["pnl_giveback_from_peak_usdt"] as? Number)?.toString() ?: "5.0"
                    pnlGivebackMinPeakUsdt = (perf.params["pnl_giveback_min_peak_usdt"] as? Number)?.toString() ?: "0.0"
                    enableEmaCrossExit = (perf.params["enable_ema_cross_exit"] as? Boolean) ?: true
                    useRsiFilter = (perf.params["use_rsi_filter"] as? Boolean) ?: false
                    rsiPeriodFilter = (perf.params["rsi_period"] as? Number)?.toString() ?: "14"
                    rsiLongMin = (perf.params["rsi_long_min"] as? Number)?.toString() ?: "50.0"
                    rsiShortMax = (perf.params["rsi_short_max"] as? Number)?.toString() ?: "50.0"
                    useAtrFilter = (perf.params["use_atr_filter"] as? Boolean) ?: false
                    atrPeriod = (perf.params["atr_period"] as? Number)?.toString() ?: "14"
                    atrMinPct = (perf.params["atr_min_pct"] as? Number)?.toString() ?: "0.0"
                    atrMaxPct = (perf.params["atr_max_pct"] as? Number)?.toString() ?: "100.0"
                    useVolumeFilter = (perf.params["use_volume_filter"] as? Boolean) ?: false
                    volumeMaPeriod = (perf.params["volume_ma_period"] as? Number)?.toString() ?: "20"
                    volumeMultiplierMin = (perf.params["volume_multiplier_min"] as? Number)?.toString() ?: "1.0"
                    useStructureFilter = (perf.params["use_structure_filter"] as? Boolean) ?: false
                    structureLeftBars = (perf.params["structure_left_bars"] as? Number)?.toString() ?: "2"
                    structureRightBars = (perf.params["structure_right_bars"] as? Number)?.toString() ?: "2"
                    structureConfirmOnClose = (perf.params["structure_confirm_on_close"] as? Boolean) ?: true
                    slTriggerMode = (perf.params["sl_trigger_mode"] as? String)?.takeIf { it in listOf("live_price", "candle_close") } ?: "live_price"
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
                    slTriggerMode = (perf.params["sl_trigger_mode"] as? String)?.takeIf { it in listOf("live_price", "candle_close") } ?: "live_price"
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
                                        pnlGivebackEnabled = false
                                        pnlGivebackFromPeakUsdt = "5.0"
                                        pnlGivebackMinPeakUsdt = "0.0"
                                        enableEmaCrossExit = true
                                        useRsiFilter = false
                                        rsiPeriodFilter = "14"
                                        rsiLongMin = "50.0"
                                        rsiShortMax = "50.0"
                                        useAtrFilter = false
                                        atrPeriod = "14"
                                        atrMinPct = "0.0"
                                        atrMaxPct = "100.0"
                                        useVolumeFilter = false
                                        volumeMaPeriod = "20"
                                        volumeMultiplierMin = "1.0"
                                        useStructureFilter = false
                                        structureLeftBars = "2"
                                        structureRightBars = "2"
                                        structureConfirmOnClose = true
                                        slTriggerMode = "live_price"
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
                                        slTriggerMode = "live_price"
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
                            checked = pnlGivebackEnabled,
                            onCheckedChange = { pnlGivebackEnabled = it }
                        )
                        Text("PnL Giveback Stop (USDT from peak)", modifier = Modifier.padding(start = Spacing.Small))
                    }
                    if (pnlGivebackEnabled) {
                        OutlinedTextField(
                            value = pnlGivebackFromPeakUsdt,
                            onValueChange = { pnlGivebackFromPeakUsdt = it },
                            label = { Text("Giveback from Peak (USDT)") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true
                        )
                        OutlinedTextField(
                            value = pnlGivebackMinPeakUsdt,
                            onValueChange = { pnlGivebackMinPeakUsdt = it },
                            label = { Text("Min Peak Unrealized (USDT)") },
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
                    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = useRsiFilter, onCheckedChange = { useRsiFilter = it })
                        Text("Use RSI Filter", modifier = Modifier.padding(start = Spacing.Small))
                    }
                    OutlinedTextField(
                        value = rsiPeriodFilter,
                        onValueChange = { if (it.all { char -> char.isDigit() }) rsiPeriodFilter = it },
                        label = { Text("RSI Period") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = rsiLongMin,
                        onValueChange = { rsiLongMin = it },
                        label = { Text("RSI Long Min") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = rsiShortMax,
                        onValueChange = { rsiShortMax = it },
                        label = { Text("RSI Short Max") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = useAtrFilter, onCheckedChange = { useAtrFilter = it })
                        Text("Use ATR Filter", modifier = Modifier.padding(start = Spacing.Small))
                    }
                    OutlinedTextField(
                        value = atrPeriod,
                        onValueChange = { if (it.all { char -> char.isDigit() }) atrPeriod = it },
                        label = { Text("ATR Period") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = atrMinPct,
                        onValueChange = { atrMinPct = it },
                        label = { Text("ATR Min %") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = atrMaxPct,
                        onValueChange = { atrMaxPct = it },
                        label = { Text("ATR Max %") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = useVolumeFilter, onCheckedChange = { useVolumeFilter = it })
                        Text("Use Volume Filter", modifier = Modifier.padding(start = Spacing.Small))
                    }
                    OutlinedTextField(
                        value = volumeMaPeriod,
                        onValueChange = { if (it.all { char -> char.isDigit() }) volumeMaPeriod = it },
                        label = { Text("Volume MA Period") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = volumeMultiplierMin,
                        onValueChange = { volumeMultiplierMin = it },
                        label = { Text("Volume Multiplier Min") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = useStructureFilter, onCheckedChange = { useStructureFilter = it })
                        Text("Use Market Structure Filter (HH/HL vs LH/LL)", modifier = Modifier.padding(start = Spacing.Small))
                    }
                    OutlinedTextField(
                        value = structureLeftBars,
                        onValueChange = { if (it.all { char -> char.isDigit() }) structureLeftBars = it },
                        label = { Text("Structure Pivot Left Bars") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = structureRightBars,
                        onValueChange = { if (it.all { char -> char.isDigit() }) structureRightBars = it },
                        label = { Text("Structure Pivot Right Bars") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = structureConfirmOnClose, onCheckedChange = { structureConfirmOnClose = it })
                        Text("Structure confirm on candle close", modifier = Modifier.padding(start = Spacing.Small))
                    }
                    Spacer(modifier = Modifier.height(Spacing.Small))
                    Text("SL Trigger", style = MaterialTheme.typography.labelMedium)
                    Row(modifier = Modifier.fillMaxWidth()) {
                        listOf("live_price" to "Live price", "candle_close" to "Candle close").forEach { (value, label) ->
                            Row(
                                modifier = Modifier.padding(end = Spacing.Medium),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                RadioButton(
                                    selected = slTriggerMode == value,
                                    onClick = { slTriggerMode = value }
                                )
                                Text(label, modifier = Modifier.padding(start = Spacing.ExtraSmall))
                            }
                        }
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
                    Spacer(modifier = Modifier.height(Spacing.Small))
                    Text("SL Trigger", style = MaterialTheme.typography.labelMedium)
                    Row(modifier = Modifier.fillMaxWidth()) {
                        listOf("live_price" to "Live price", "candle_close" to "Candle close").forEach { (value, label) ->
                            Row(
                                modifier = Modifier.padding(end = Spacing.Medium),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                RadioButton(
                                    selected = slTriggerMode == value,
                                    onClick = { slTriggerMode = value }
                                )
                                Text(label, modifier = Modifier.padding(start = Spacing.ExtraSmall))
                            }
                        }
                    }
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
                            pnlGivebackEnabled = pnlGivebackEnabled,
                            pnlGivebackFromPeakUsdt = pnlGivebackFromPeakUsdt,
                            pnlGivebackMinPeakUsdt = pnlGivebackMinPeakUsdt,
                            enableEmaCrossExit = enableEmaCrossExit,
                            useRsiFilter = useRsiFilter,
                            rsiPeriodFilter = rsiPeriodFilter,
                            rsiLongMin = rsiLongMin,
                            rsiShortMax = rsiShortMax,
                            useAtrFilter = useAtrFilter,
                            atrPeriod = atrPeriod,
                            atrMinPct = atrMinPct,
                            atrMaxPct = atrMaxPct,
                            useVolumeFilter = useVolumeFilter,
                            volumeMaPeriod = volumeMaPeriod,
                            volumeMultiplierMin = volumeMultiplierMin,
                            useStructureFilter = useStructureFilter,
                            structureLeftBars = structureLeftBars,
                            structureRightBars = structureRightBars,
                            structureConfirmOnClose = structureConfirmOnClose,
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
                            slBufferPct = slBufferPct,
                            slTriggerMode = slTriggerMode
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
    pnlGivebackEnabled: Boolean = false,
    pnlGivebackFromPeakUsdt: String = "5.0",
    pnlGivebackMinPeakUsdt: String = "0.0",
    enableEmaCrossExit: Boolean = true,
    useRsiFilter: Boolean = false,
    rsiPeriodFilter: String = "14",
    rsiLongMin: String = "50.0",
    rsiShortMax: String = "50.0",
    useAtrFilter: Boolean = false,
    atrPeriod: String = "14",
    atrMinPct: String = "0.0",
    atrMaxPct: String = "100.0",
    useVolumeFilter: Boolean = false,
    volumeMaPeriod: String = "20",
    volumeMultiplierMin: String = "1.0",
    useStructureFilter: Boolean = false,
    structureLeftBars: String = "2",
    structureRightBars: String = "2",
    structureConfirmOnClose: Boolean = true,
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
    slBufferPct: String = "0.002",
    slTriggerMode: String = "live_price"
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
                "pnl_giveback_enabled" to pnlGivebackEnabled,
                "pnl_giveback_from_peak_usdt" to (pnlGivebackFromPeakUsdt.toDoubleOrNull() ?: 5.0),
                "pnl_giveback_min_peak_usdt" to (pnlGivebackMinPeakUsdt.toDoubleOrNull() ?: 0.0),
                "enable_ema_cross_exit" to enableEmaCrossExit,
                "use_rsi_filter" to useRsiFilter,
                "rsi_period" to (rsiPeriodFilter.toIntOrNull() ?: 14),
                "rsi_long_min" to (rsiLongMin.toDoubleOrNull() ?: 50.0),
                "rsi_short_max" to (rsiShortMax.toDoubleOrNull() ?: 50.0),
                "use_atr_filter" to useAtrFilter,
                "atr_period" to (atrPeriod.toIntOrNull() ?: 14),
                "atr_min_pct" to (atrMinPct.toDoubleOrNull() ?: 0.0),
                "atr_max_pct" to (atrMaxPct.toDoubleOrNull() ?: 100.0),
                "use_volume_filter" to useVolumeFilter,
                "volume_ma_period" to (volumeMaPeriod.toIntOrNull() ?: 20),
                "volume_multiplier_min" to (volumeMultiplierMin.toDoubleOrNull() ?: 1.0),
                "use_structure_filter" to useStructureFilter,
                "structure_left_bars" to (structureLeftBars.toIntOrNull() ?: 2),
                "structure_right_bars" to (structureRightBars.toIntOrNull() ?: 2),
                "structure_confirm_on_close" to structureConfirmOnClose,
                "sl_trigger_mode" to (if (slTriggerMode in listOf("live_price", "candle_close")) slTriggerMode else "live_price")
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
                "cooldown_candles" to (cooldownCandles.toIntOrNull() ?: 2),
                "sl_trigger_mode" to (if (slTriggerMode in listOf("live_price", "candle_close")) slTriggerMode else "live_price")
            )
        }
        else -> emptyMap()
    }
}

