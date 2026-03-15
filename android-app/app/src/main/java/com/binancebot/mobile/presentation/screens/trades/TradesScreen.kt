@file:OptIn(ExperimentalMaterial3Api::class)

package com.binancebot.mobile.presentation.screens.trades

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.presentation.components.BottomNavigationBar
import com.binancebot.mobile.presentation.components.OfflineIndicator
import com.binancebot.mobile.presentation.components.shouldShowBottomNav
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.viewmodel.TradesViewModel
import com.binancebot.mobile.presentation.viewmodel.AccountViewModel
import com.binancebot.mobile.domain.model.Account

@Composable
fun TradesScreen(
    navController: NavController,
    viewModel: TradesViewModel = hiltViewModel(),
    accountViewModel: AccountViewModel = hiltViewModel()
) {
    val currentRoute = navController.currentDestination?.route
    val allOpenPositions by viewModel.allOpenPositions.collectAsState()
    val pnlLoading by viewModel.pnlLoading.collectAsState()
    val manualCloseInProgress by viewModel.manualCloseInProgress.collectAsState()
    val manualCloseError by viewModel.manualCloseError.collectAsState()
    val manualTradeLoading by viewModel.manualTradeLoading.collectAsState()
    val manualTradeError by viewModel.manualTradeError.collectAsState()
    val manualTradeSuccess by viewModel.manualTradeSuccess.collectAsState()
    val accounts by accountViewModel.accounts.collectAsState()
    val isOnline = remember { mutableStateOf(true) }
    val lastSyncTime = remember { mutableStateOf<Long?>(null) }
    val snackbarHostState = remember { SnackbarHostState() }
    var showManualTradeDialog by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        viewModel.loadPnLOverview()
        accountViewModel.loadAccounts()
    }

    LaunchedEffect(manualCloseError) {
        manualCloseError?.let { msg ->
            snackbarHostState.showSnackbar(message = msg, actionLabel = "Dismiss")
            viewModel.clearManualCloseError()
        }
    }
    
    LaunchedEffect(manualTradeError) {
        manualTradeError?.let { msg ->
            snackbarHostState.showSnackbar(message = msg, actionLabel = "Dismiss")
            viewModel.clearManualTradeMessages()
        }
    }
    
    LaunchedEffect(manualTradeSuccess) {
        manualTradeSuccess?.let { msg ->
            snackbarHostState.showSnackbar(message = msg)
            viewModel.clearManualTradeMessages()
            showManualTradeDialog = false
        }
    }

    // Manual Trade Dialog: show all accounts (live + paper) like web app
    if (showManualTradeDialog) {
        ManualTradeDialog(
            accounts = accounts,
            onDismiss = { showManualTradeDialog = false },
            onSubmit = { symbol, side, usdtAmount, leverage, accountId, marginType, tpPct, slPct, tpPrice, slPrice, trailingEnabled, trailingRate, notes ->
                viewModel.openManualPosition(
                    symbol = symbol,
                    side = side,
                    usdtAmount = usdtAmount,
                    leverage = leverage,
                    accountId = accountId,
                    marginType = marginType,
                    takeProfitPct = tpPct,
                    stopLossPct = slPct,
                    tpPrice = tpPrice,
                    slPrice = slPrice,
                    trailingStopEnabled = trailingEnabled,
                    trailingStopCallbackRate = trailingRate,
                    notes = notes
                )
            },
            isLoading = manualTradeLoading
        )
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = {
            TopAppBar(
                title = { Text("Open Positions") },
                actions = {
                    IconButton(onClick = { viewModel.loadPnLOverview() }) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh"
                        )
                    }
                }
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { showManualTradeDialog = true },
                containerColor = MaterialTheme.colorScheme.primary
            ) {
                Icon(Icons.Default.Add, contentDescription = "New Position")
            }
        },
        bottomBar = {
            if (shouldShowBottomNav(currentRoute)) {
                BottomNavigationBar(
                    currentRoute = currentRoute,
                    onNavigate = { route ->
                        navController.navigate(route) {
                            popUpTo(Screen.Home.route) { inclusive = false }
                            launchSingleTop = true
                        }
                    }
                )
            }
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            OfflineIndicator(
                isOnline = isOnline.value,
                lastSyncTime = lastSyncTime.value,
                modifier = Modifier.fillMaxWidth()
            )
            
            PositionsTab(
                positions = allOpenPositions,
                isLoading = pnlLoading,
                onRefresh = { viewModel.loadPnLOverview() },
                onStrategyClick = { strategyId ->
                    if (strategyId.startsWith("manual_")) {
                        val positionId = strategyId.removePrefix("manual_")
                        val position = allOpenPositions.find { it.strategyId == strategyId }
                        viewModel.closeManualPositionById(positionId, position?.accountId)
                    } else {
                        navController.navigate("strategy_details/$strategyId")
                    }
                },
                onManualClose = { position ->
                    val strategyId = position.strategyId ?: return@PositionsTab
                    if (strategyId.startsWith("external_")) return@PositionsTab
                    if (strategyId.startsWith("manual_")) {
                        val positionId = strategyId.removePrefix("manual_")
                        viewModel.closeManualPositionById(positionId, position.accountId)
                    } else {
                        viewModel.manualClosePosition(
                            strategyId = strategyId,
                            symbol = position.symbol,
                            positionSide = position.positionSide,
                            accountId = position.accountId
                        )
                    }
                },
                manualCloseInProgressStrategyId = manualCloseInProgress,
                modifier = Modifier.fillMaxSize()
            )
        }
    }
}

/**
 * Dialog for opening a manual position
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ManualTradeDialog(
    accounts: List<Account>,
    onDismiss: () -> Unit,
    onSubmit: (
        symbol: String,
        side: String,
        usdtAmount: Double,
        leverage: Int,
        accountId: String,
        marginType: String,
        tpPct: Double?,
        slPct: Double?,
        tpPrice: Double?,
        slPrice: Double?,
        trailingEnabled: Boolean,
        trailingRate: Double?,
        notes: String?
    ) -> Unit,
    isLoading: Boolean
) {
    var symbol by remember { mutableStateOf("") }
    var side by remember { mutableStateOf("LONG") }
    var usdtAmount by remember { mutableStateOf("") }
    var leverage by remember { mutableStateOf("10") }
    var marginType by remember { mutableStateOf("CROSSED") }
    var tpPct by remember { mutableStateOf("") }
    var slPct by remember { mutableStateOf("") }
    var tpPrice by remember { mutableStateOf("") }
    var slPrice by remember { mutableStateOf("") }
    var trailingEnabled by remember { mutableStateOf(false) }
    var trailingRate by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var selectedAccountId by remember { mutableStateOf(accounts.firstOrNull()?.accountId ?: "default") }
    var showAccountDropdown by remember { mutableStateOf(false) }
    var showMarginDropdown by remember { mutableStateOf(false) }
    
    // Update selected account when accounts load
    LaunchedEffect(accounts) {
        if (accounts.isNotEmpty() && selectedAccountId == "default") {
            selectedAccountId = accounts.first().accountId
        }
    }
    
    AlertDialog(
        onDismissRequest = { if (!isLoading) onDismiss() },
        title = { Text("Open Manual Position", fontWeight = FontWeight.Bold) },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Symbol
                OutlinedTextField(
                    value = symbol,
                    onValueChange = { symbol = it.uppercase() },
                    label = { Text("Symbol") },
                    placeholder = { Text("e.g., BTCUSDT") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                
                // Side selector
                Text("Side", style = MaterialTheme.typography.labelMedium)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = { side = "LONG" },
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (side == "LONG") Color(0xFF28A745) else Color.Gray
                        )
                    ) {
                        Text("LONG")
                    }
                    Button(
                        onClick = { side = "SHORT" },
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (side == "SHORT") Color(0xFFDC3545) else Color.Gray
                        )
                    ) {
                        Text("SHORT")
                    }
                }
                
                // Account selector
                if (accounts.isNotEmpty()) {
                    ExposedDropdownMenuBox(
                        expanded = showAccountDropdown,
                        onExpandedChange = { showAccountDropdown = it }
                    ) {
                        OutlinedTextField(
                            value = accounts.find { it.accountId == selectedAccountId }?.let { acc ->
                                buildString {
                                    append(acc.name ?: acc.accountId)
                                    if (acc.paperTrading) append(" [PAPER]")
                                    if (acc.testnet) append(" [TESTNET]")
                                }
                            } ?: selectedAccountId,
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Account") },
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
                                    text = {
                                        Text(
                                            buildString {
                                                append(account.name ?: account.accountId)
                                                if (account.paperTrading) append(" [PAPER]")
                                                if (account.testnet) append(" [TESTNET]")
                                            }
                                        )
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
                
                // USDT Amount & Leverage
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedTextField(
                        value = usdtAmount,
                        onValueChange = { usdtAmount = it },
                        label = { Text("Amount (USDT)") },
                        placeholder = { Text("e.g., 100") },
                        modifier = Modifier.weight(1f),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal)
                    )
                    OutlinedTextField(
                        value = leverage,
                        onValueChange = { leverage = it },
                        label = { Text("Leverage") },
                        modifier = Modifier.weight(1f),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
                    )
                }
                
                // Margin Type selector
                ExposedDropdownMenuBox(
                    expanded = showMarginDropdown,
                    onExpandedChange = { showMarginDropdown = it }
                ) {
                    OutlinedTextField(
                        value = marginType,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Margin Type") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = showMarginDropdown) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        singleLine = true
                    )
                    ExposedDropdownMenu(
                        expanded = showMarginDropdown,
                        onDismissRequest = { showMarginDropdown = false }
                    ) {
                        listOf("CROSSED", "ISOLATED").forEach { type ->
                            DropdownMenuItem(
                                text = { Text(type) },
                                onClick = {
                                    marginType = type
                                    showMarginDropdown = false
                                }
                            )
                        }
                    }
                }
                
                // TP/SL Percentages
                Text("TP/SL % (Optional)", style = MaterialTheme.typography.labelMedium)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedTextField(
                        value = tpPct,
                        onValueChange = { tpPct = it },
                        label = { Text("TP %") },
                        placeholder = { Text("2") },
                        modifier = Modifier.weight(1f),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal)
                    )
                    OutlinedTextField(
                        value = slPct,
                        onValueChange = { slPct = it },
                        label = { Text("SL %") },
                        placeholder = { Text("1") },
                        modifier = Modifier.weight(1f),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal)
                    )
                }
                
                // TP/SL Absolute Prices (overrides %)
                Text("TP/SL Price (overrides %)", style = MaterialTheme.typography.labelSmall, color = Color.Gray)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedTextField(
                        value = tpPrice,
                        onValueChange = { tpPrice = it },
                        label = { Text("TP Price") },
                        placeholder = { Text("Optional") },
                        modifier = Modifier.weight(1f),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal)
                    )
                    OutlinedTextField(
                        value = slPrice,
                        onValueChange = { slPrice = it },
                        label = { Text("SL Price") },
                        placeholder = { Text("Optional") },
                        modifier = Modifier.weight(1f),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal)
                    )
                }
                
                // Trailing Stop
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Checkbox(
                        checked = trailingEnabled,
                        onCheckedChange = { trailingEnabled = it }
                    )
                    Text("Enable Trailing Stop", style = MaterialTheme.typography.bodyMedium)
                }
                
                if (trailingEnabled) {
                    OutlinedTextField(
                        value = trailingRate,
                        onValueChange = { trailingRate = it },
                        label = { Text("Callback Rate %") },
                        placeholder = { Text("e.g., 1 for 1%") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal)
                    )
                }
                
                // Notes
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    label = { Text("Notes (Optional)") },
                    placeholder = { Text("Trade notes...") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                
                if (isLoading) {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val amount = usdtAmount.toDoubleOrNull() ?: return@Button
                    val lev = leverage.toIntOrNull() ?: 10
                    val tp = tpPct.toDoubleOrNull()?.let { it / 100 }
                    val sl = slPct.toDoubleOrNull()?.let { it / 100 }
                    val tpPriceVal = tpPrice.toDoubleOrNull()
                    val slPriceVal = slPrice.toDoubleOrNull()
                    val trailingRateVal = if (trailingEnabled) trailingRate.toDoubleOrNull() else null
                    val notesVal = notes.ifBlank { null }
                    onSubmit(
                        symbol.trim(),
                        side,
                        amount,
                        lev,
                        selectedAccountId,
                        marginType,
                        tp,
                        sl,
                        tpPriceVal,
                        slPriceVal,
                        trailingEnabled,
                        trailingRateVal,
                        notesVal
                    )
                },
                enabled = !isLoading && symbol.isNotBlank() && usdtAmount.toDoubleOrNull() != null
            ) {
                Text(if (isLoading) "Opening..." else "Open Position")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !isLoading) {
                Text("Cancel")
            }
        }
    )
}
