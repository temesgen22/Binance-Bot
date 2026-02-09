package com.binancebot.mobile.presentation.screens.testaccounts

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
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.TestAccountsViewModel
import com.binancebot.mobile.presentation.viewmodel.TestAccountsUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TestAccountsScreen(
    navController: NavController,
    viewModel: TestAccountsViewModel = hiltViewModel()
) {
    val testResult by viewModel.testResult.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
    var showTestDialog by remember { mutableStateOf(false) }
    var showQuickTestDialog by remember { mutableStateOf(false) }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Test Accounts") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        },
        floatingActionButton = {
            Row(
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                FloatingActionButton(
                    onClick = { showQuickTestDialog = true },
                    modifier = Modifier.size(56.dp)
                ) {
                    Icon(Icons.Default.Bolt, contentDescription = "Quick Test")
                }
                FloatingActionButton(
                    onClick = { showTestDialog = true }
                ) {
                    Icon(Icons.Default.Add, contentDescription = "Test Account")
                }
            }
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(Spacing.ScreenPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            // Info Card
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(Spacing.Medium),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Default.Info,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                    Spacer(modifier = Modifier.width(Spacing.Small))
                    Text(
                        text = "Test your Binance API credentials before adding them as accounts.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                }
            }
            
            // Test Result Display
            testResult?.let { result ->
                TestResultCard(
                    result = result,
                    modifier = Modifier.fillMaxWidth()
                )
            }
            
            // Instructions
            Card(
                modifier = Modifier.fillMaxWidth(),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(Spacing.CardPadding),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    Text(
                        text = "How to Test Accounts",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Divider()
                    
                    InstructionItem(
                        number = "1",
                        text = "Click the '+' button to test with account name"
                    )
                    InstructionItem(
                        number = "2",
                        text = "Click the lightning bolt for quick test (API key/secret only)"
                    )
                    InstructionItem(
                        number = "3",
                        text = "Review the test results before adding to accounts"
                    )
                }
            }
        }
        
        // Test Account Dialog
        if (showTestDialog) {
            TestAccountDialog(
                onDismiss = { showTestDialog = false },
                onTest = { request ->
                    viewModel.testAccount(request)
                    showTestDialog = false
                },
                isLoading = uiState is TestAccountsUiState.Loading
            )
        }
        
        // Quick Test Dialog
        if (showQuickTestDialog) {
            QuickTestAccountDialog(
                onDismiss = { showQuickTestDialog = false },
                onTest = { apiKey, apiSecret, testnet ->
                    viewModel.quickTestAccount(apiKey, apiSecret, testnet)
                    showQuickTestDialog = false
                },
                isLoading = uiState is TestAccountsUiState.Loading
            )
        }
    }
}

@Composable
fun TestResultCard(
    result: com.binancebot.mobile.data.remote.dto.TestAccountResponseDto,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier,
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (result.success) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.errorContainer
            }
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.CardPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Test Result",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                Surface(
                    shape = MaterialTheme.shapes.small,
                    color = if (result.success) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.error
                    }
                ) {
                    Text(
                        text = if (result.success) "✅ Success" else "❌ Failed",
                        modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (result.success) {
                            MaterialTheme.colorScheme.onPrimary
                        } else {
                            MaterialTheme.colorScheme.onError
                        }
                    )
                }
            }
            
            Divider()
            
            result.accountName?.let {
                MetricRow("Account Name", it)
            }
            
            MetricRow("Testnet", if (result.testnet) "Yes" else "No")
            MetricRow("Connection Status", result.connectionStatus)
            MetricRow("Authentication Status", result.authenticationStatus)
            
            result.balance?.let {
                MetricRow("Balance", FormatUtils.formatCurrency(it))
            }
            
            result.error?.let {
                Text(
                    text = "Error: $it",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error
                )
            }
        }
    }
}

@Composable
fun InstructionItem(
    number: String,
    text: String
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Surface(
            shape = MaterialTheme.shapes.small,
            color = MaterialTheme.colorScheme.primaryContainer
        ) {
            Text(
                text = number,
                modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onPrimaryContainer
            )
        }
        Spacer(modifier = Modifier.width(Spacing.Small))
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium
        )
    }
}

@Composable
fun MetricRow(
    label: String,
    value: String,
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
            fontWeight = FontWeight.Bold
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TestAccountDialog(
    onDismiss: () -> Unit,
    onTest: (com.binancebot.mobile.data.remote.dto.TestAccountRequestDto) -> Unit,
    isLoading: Boolean
) {
    var accountName by remember { mutableStateOf("") }
    var apiKey by remember { mutableStateOf("") }
    var apiSecret by remember { mutableStateOf("") }
    var testnet by remember { mutableStateOf(true) }
    var showApiSecret by remember { mutableStateOf(false) }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Test Account") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                OutlinedTextField(
                    value = accountName,
                    onValueChange = { accountName = it },
                    label = { Text("Account Name (Optional)") },
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = apiKey,
                    onValueChange = { apiKey = it },
                    label = { Text("API Key *") },
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = apiSecret,
                    onValueChange = { apiSecret = it },
                    label = { Text("API Secret *") },
                    modifier = Modifier.fillMaxWidth(),
                    visualTransformation = if (showApiSecret) {
                        androidx.compose.ui.text.input.VisualTransformation.None
                    } else {
                        androidx.compose.ui.text.input.PasswordVisualTransformation()
                    },
                    trailingIcon = {
                        IconButton(onClick = { showApiSecret = !showApiSecret }) {
                            Icon(
                                imageVector = if (showApiSecret) Icons.Default.Visibility else Icons.Default.VisibilityOff,
                                contentDescription = if (showApiSecret) "Hide" else "Show"
                            )
                        }
                    }
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("Testnet")
                    Switch(
                        checked = testnet,
                        onCheckedChange = { testnet = it }
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (apiKey.isNotBlank() && apiSecret.isNotBlank()) {
                        onTest(
                            com.binancebot.mobile.data.remote.dto.TestAccountRequestDto(
                                apiKey = apiKey,
                                apiSecret = apiSecret,
                                testnet = testnet,
                                accountName = accountName.takeIf { it.isNotBlank() }
                            )
                        )
                    }
                },
                enabled = apiKey.isNotBlank() && apiSecret.isNotBlank() && !isLoading
            ) {
                if (isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("Test")
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun QuickTestAccountDialog(
    onDismiss: () -> Unit,
    onTest: (String, String, Boolean) -> Unit,
    isLoading: Boolean
) {
    var apiKey by remember { mutableStateOf("") }
    var apiSecret by remember { mutableStateOf("") }
    var testnet by remember { mutableStateOf(true) }
    var showApiSecret by remember { mutableStateOf(false) }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Quick Test Account") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                Text(
                    text = "Quick test with API credentials only (no account name required).",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                OutlinedTextField(
                    value = apiKey,
                    onValueChange = { apiKey = it },
                    label = { Text("API Key *") },
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = apiSecret,
                    onValueChange = { apiSecret = it },
                    label = { Text("API Secret *") },
                    modifier = Modifier.fillMaxWidth(),
                    visualTransformation = if (showApiSecret) {
                        androidx.compose.ui.text.input.VisualTransformation.None
                    } else {
                        androidx.compose.ui.text.input.PasswordVisualTransformation()
                    },
                    trailingIcon = {
                        IconButton(onClick = { showApiSecret = !showApiSecret }) {
                            Icon(
                                imageVector = if (showApiSecret) Icons.Default.Visibility else Icons.Default.VisibilityOff,
                                contentDescription = if (showApiSecret) "Hide" else "Show"
                            )
                        }
                    }
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("Testnet")
                    Switch(
                        checked = testnet,
                        onCheckedChange = { testnet = it }
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (apiKey.isNotBlank() && apiSecret.isNotBlank()) {
                        onTest(apiKey, apiSecret, testnet)
                    }
                },
                enabled = apiKey.isNotBlank() && apiSecret.isNotBlank() && !isLoading
            ) {
                if (isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("Quick Test")
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}
