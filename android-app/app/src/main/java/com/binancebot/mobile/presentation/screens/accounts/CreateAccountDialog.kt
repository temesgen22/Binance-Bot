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
    onCreate: (String, String, String, Boolean) -> Unit
) {
    var accountName by remember { mutableStateOf("") }
    var apiKey by remember { mutableStateOf("") }
    var apiSecret by remember { mutableStateOf("") }
    var testnet by remember { mutableStateOf(false) }
    var showApiSecret by remember { mutableStateOf(false) }
    
    // Reset state when dialog is dismissed
    val resetState = {
        accountName = ""
        apiKey = ""
        apiSecret = ""
        testnet = false
        showApiSecret = false
    }
    
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
                    value = accountName,
                    onValueChange = { accountName = it },
                    label = { Text("Account Name *") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    isError = accountName.isBlank()
                )
                
                OutlinedTextField(
                    value = apiKey,
                    onValueChange = { apiKey = it },
                    label = { Text("API Key *") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    isError = apiKey.isBlank()
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
                    isError = apiSecret.isBlank()
                )
                
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                ) {
                    Checkbox(
                        checked = testnet,
                        onCheckedChange = { testnet = it }
                    )
                    Text(
                        text = "Testnet Account",
                        modifier = Modifier.padding(start = Spacing.Small)
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onCreate(accountName.trim(), apiKey.trim(), apiSecret.trim(), testnet)
                    resetState()
                },
                enabled = accountName.isNotBlank() && apiKey.isNotBlank() && apiSecret.isNotBlank()
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

