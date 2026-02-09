package com.binancebot.mobile.presentation.screens.strategies

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.data.remote.dto.UpdateStrategyRequest
import com.binancebot.mobile.domain.model.Strategy

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EditStrategyDialog(
    strategy: Strategy,
    onDismiss: () -> Unit,
    onConfirm: (UpdateStrategyRequest) -> Unit
) {
    // Initialize state from strategy
    var name by remember(strategy.id) { mutableStateOf(strategy.name) }
    var symbol by remember(strategy.id) { mutableStateOf(strategy.symbol) }
    var leverage by remember(strategy.id) { mutableStateOf(strategy.leverage.toString()) }
    var riskPerTrade by remember(strategy.id) { mutableStateOf(strategy.riskPerTrade?.toString() ?: "") }
    var fixedAmount by remember(strategy.id) { mutableStateOf(strategy.fixedAmount?.toString() ?: "") }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Edit Strategy") },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Strategy Name") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                
                OutlinedTextField(
                    value = symbol,
                    onValueChange = { symbol = it },
                    label = { Text("Symbol (e.g., BTCUSDT)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                
                OutlinedTextField(
                    value = leverage,
                    onValueChange = { leverage = it },
                    label = { Text("Leverage") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                
                OutlinedTextField(
                    value = riskPerTrade,
                    onValueChange = { riskPerTrade = it },
                    label = { Text("Risk Per Trade (0.01 = 1%)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                
                OutlinedTextField(
                    value = fixedAmount,
                    onValueChange = { fixedAmount = it },
                    label = { Text("Fixed Amount (optional)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val request = UpdateStrategyRequest(
                        name = if (name != strategy.name) name else null,
                        symbol = if (symbol != strategy.symbol) symbol.uppercase() else null,
                        leverage = leverage.toIntOrNull()?.takeIf { it != strategy.leverage },
                        riskPerTrade = riskPerTrade.toDoubleOrNull()?.takeIf { it != strategy.riskPerTrade },
                        fixedAmount = fixedAmount.toDoubleOrNull()?.takeIf { it != strategy.fixedAmount }
                    )
                    onConfirm(request)
                },
                enabled = name.isNotBlank() && symbol.isNotBlank()
            ) {
                Text("Update")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}























