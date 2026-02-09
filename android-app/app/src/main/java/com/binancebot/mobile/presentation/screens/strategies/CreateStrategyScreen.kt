package com.binancebot.mobile.presentation.screens.strategies

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.domain.model.Account
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.viewmodel.AccountViewModel
import com.binancebot.mobile.presentation.viewmodel.StrategiesViewModel

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
    
    val accounts by accountViewModel.accounts.collectAsState()
    val uiState by strategiesViewModel.uiState.collectAsState()
    
    // Auto-select first account if available
    LaunchedEffect(accounts) {
        if (accounts.isNotEmpty() && selectedAccountId == null) {
            selectedAccountId = accounts.first().accountId
        }
    }
    
    // Navigate back on success
    LaunchedEffect(uiState) {
        if (uiState is com.binancebot.mobile.presentation.viewmodel.StrategiesUiState.Success) {
            navController.popBackStack()
        }
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Create Strategy") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
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
                    listOf("scalping", "range_mean_reversion").forEach { type ->
                        DropdownMenuItem(
                            text = { Text(type.replace("_", " ").replaceFirstChar { it.uppercase() }) },
                            onClick = {
                                strategyType = type
                                showStrategyTypeDropdown = false
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
            val isValid = name.isNotBlank() &&
                    symbol.isNotBlank() &&
                    leverage.toIntOrNull()?.let { it in 1..50 } == true &&
                    selectedAccountId != null &&
                    (riskPerTrade.toDoubleOrNull() != null || fixedAmount.toDoubleOrNull() != null) &&
                    uiState !is com.binancebot.mobile.presentation.viewmodel.StrategiesUiState.Loading
            
            Button(
                onClick = {
                    selectedAccountId?.let { accountId ->
                        strategiesViewModel.createStrategy(
                            name = name.trim(),
                            symbol = symbol.trim().uppercase(),
                            strategyType = strategyType,
                            leverage = leverage.toInt(),
                            riskPerTrade = riskPerTrade.toDoubleOrNull(),
                            fixedAmount = fixedAmount.toDoubleOrNull(),
                            accountId = accountId
                        )
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = isValid
            ) {
                if (uiState is com.binancebot.mobile.presentation.viewmodel.StrategiesUiState.Loading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        color = MaterialTheme.colorScheme.onPrimary
                    )
                    Spacer(modifier = Modifier.width(Spacing.Small))
                }
                Text("Create Strategy")
            }
        }
    }
}

