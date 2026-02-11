package com.binancebot.mobile.presentation.screens.accounts

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.presentation.theme.Spacing

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CreateAccountDialog(
    onDismiss: () -> Unit,
    onCreate: (String, String?, String?, String?, Boolean, Boolean, Double?) -> Unit
) {
    var accountId by remember { mutableStateOf("") }
    var accountName by remember { mutableStateOf("") }
    var apiKey by remember { mutableStateOf("") }
    var apiSecret by remember { mutableStateOf("") }
    var testnet by remember { mutableStateOf(true) }
    var paperTrading by remember { mutableStateOf(false) }
    var paperBalance by remember { mutableStateOf("10000") }
    var showApiSecret by remember { mutableStateOf(false) }
    
    // Reset state when dialog is dismissed
    val resetState = {
        accountId = ""
        accountName = ""
        apiKey = ""
        apiSecret = ""
        testnet = true
        paperTrading = false
        paperBalance = "10000"
        showApiSecret = false
    }
    
    // When paper trading is enabled, API keys become optional
    val isApiKeyRequired = !paperTrading
    
    AlertDialog(
        onDismissRequest = {
            resetState()
            onDismiss()
        },
        title = { Text("Add Binance Account") },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                OutlinedTextField(
                    value = accountId,
                    onValueChange = { accountId = it.lowercase().replace(" ", "_") },
                    label = { Text("Account ID *") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    supportingText = { Text("Unique identifier (lowercase, alphanumeric, underscores)") },
                    isError = accountId.isBlank() || !accountId.matches(Regex("^[a-z0-9_-]+$"))
                )
                
                OutlinedTextField(
                    value = accountName,
                    onValueChange = { accountName = it },
                    label = { Text("Account Name (Optional)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    supportingText = { Text("Display name for the account") }
                )
                
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                ) {
                    Checkbox(
                        checked = paperTrading,
                        onCheckedChange = { paperTrading = it }
                    )
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Paper Trading",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                        )
                        Text(
                            text = "Simulated trading (no real API keys needed)",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                
                if (paperTrading) {
                    OutlinedTextField(
                        value = paperBalance,
                        onValueChange = { if (it.all { char -> char.isDigit() || char == '.' }) paperBalance = it },
                        label = { Text("Initial Paper Balance (USDT)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        supportingText = { Text("Default: 10000 USDT") }
                    )
                }
                
                if (!paperTrading) {
                    HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                    Text(
                        text = "API Credentials (Required for Live Trading)",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                    )
                    
                    OutlinedTextField(
                        value = apiKey,
                        onValueChange = { apiKey = it },
                        label = { Text("API Key *") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        isError = isApiKeyRequired && apiKey.isBlank()
                    )
                    
                    OutlinedTextField(
                        value = apiSecret,
                        onValueChange = { apiSecret = it },
                        label = { Text("API Secret *") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        visualTransformation = if (showApiSecret) {
                            androidx.compose.ui.text.input.VisualTransformation.None
                        } else {
                            androidx.compose.ui.text.input.PasswordVisualTransformation()
                        },
                        trailingIcon = {
                            IconButton(onClick = { showApiSecret = !showApiSecret }) {
                                Icon(
                                    imageVector = if (showApiSecret) {
                                        Icons.Default.Visibility
                                    } else {
                                        Icons.Default.VisibilityOff
                                    },
                                    contentDescription = if (showApiSecret) "Hide" else "Show"
                                )
                            }
                        },
                        isError = isApiKeyRequired && apiSecret.isBlank()
                    )
                }
                
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                ) {
                    Checkbox(
                        checked = testnet,
                        onCheckedChange = { testnet = it },
                        enabled = !paperTrading // Testnet only applies to live trading
                    )
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Testnet Account",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                        )
                        Text(
                            text = if (paperTrading) "Not applicable for paper trading" else "Use Binance testnet",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val accountIdValue = accountId.trim().ifBlank { accountName.trim().lowercase().replace(" ", "_") }
                    val nameValue = accountName.trim().takeIf { it.isNotBlank() }
                    val apiKeyValue = apiKey.trim().takeIf { it.isNotBlank() }
                    val apiSecretValue = apiSecret.trim().takeIf { it.isNotBlank() }
                    val paperBalanceValue = if (paperTrading) paperBalance.toDoubleOrNull() ?: 10000.0 else null
                    
                    onCreate(
                        accountIdValue,
                        nameValue,
                        apiKeyValue,
                        apiSecretValue,
                        testnet,
                        paperTrading,
                        paperBalanceValue
                    )
                    resetState()
                },
                enabled = accountId.isNotBlank() && accountId.matches(Regex("^[a-z0-9_-]+$")) &&
                        (!isApiKeyRequired || (apiKey.isNotBlank() && apiSecret.isNotBlank()))
            ) {
                Text("Add Account")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

