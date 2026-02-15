package com.binancebot.mobile.presentation.screens.pricealerts

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.presentation.viewmodel.PriceAlertFormUiState

private val alertTypes = listOf(
    "PRICE_RISES_ABOVE" to "Rises above",
    "PRICE_DROPS_BELOW" to "Drops below",
    "PRICE_REACHES" to "Reaches"
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PriceAlertFormScreen(
    navController: NavController,
    viewModel: PriceAlertFormViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val symbol by viewModel.symbol.collectAsState()
    val alertType by viewModel.alertType.collectAsState()
    val targetPrice by viewModel.targetPrice.collectAsState()
    val triggerOnce by viewModel.triggerOnce.collectAsState()
    var errorMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(uiState) {
        when (uiState) {
            is PriceAlertFormUiState.SaveSuccess -> navController.popBackStack()
            is PriceAlertFormUiState.Error ->
                errorMessage = (uiState as PriceAlertFormUiState.Error).message
            else -> {}
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        if (viewModel.alertId != null) "Edit price alert" else "Add price alert"
                    )
                },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        when (uiState) {
            is PriceAlertFormUiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = androidx.compose.ui.Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
            is PriceAlertFormUiState.Error -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = androidx.compose.ui.Alignment.Center
                ) {
                    Column(
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text(
                            text = (uiState as PriceAlertFormUiState.Error).message,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.error
                        )
                        TextButton(onClick = { navController.popBackStack() }) {
                            Text("Back")
                        }
                    }
                }
            }
            else -> {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                        .verticalScroll(rememberScrollState())
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    OutlinedTextField(
                        value = symbol,
                        onValueChange = { viewModel.setSymbol(it) },
                        label = { Text("Symbol") },
                        placeholder = { Text("e.g. BTCUSDT") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    var expanded by remember { mutableStateOf(false) }
                    val selectedLabel = alertTypes.find { it.first == alertType }?.second ?: alertType
                    ExposedDropdownMenuBox(
                        expanded = expanded,
                        onExpandedChange = { expanded = it }
                    ) {
                        OutlinedTextField(
                            value = selectedLabel,
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Alert type") },
                            modifier = Modifier
                                .fillMaxWidth()
                                .menuAnchor(),
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) }
                        )
                        ExposedDropdownMenu(
                            expanded = expanded,
                            onDismissRequest = { expanded = false }
                        ) {
                            alertTypes.forEach { (value, label) ->
                                DropdownMenuItem(
                                    text = { Text(label) },
                                    onClick = {
                                        viewModel.setAlertType(value)
                                        expanded = false
                                    }
                                )
                            }
                        }
                    }
                    OutlinedTextField(
                        value = targetPrice,
                        onValueChange = { viewModel.setTargetPrice(it) },
                        label = { Text("Target price") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal)
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = triggerOnce,
                            onCheckedChange = { viewModel.setTriggerOnce(it) }
                        )
                        Text(
                            text = "Trigger once (disable after first alert)",
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                    errorMessage?.let { msg ->
                        Text(
                            text = msg,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error
                        )
                        errorMessage = null
                    }
                    if (uiState is PriceAlertFormUiState.Saving) {
                        LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                    }
                    Button(
                        onClick = {
                            viewModel.save(
                                onSuccess = { },
                                onError = { errorMessage = it }
                            )
                        },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = uiState !is PriceAlertFormUiState.Saving
                    ) {
                        Text("Save")
                    }
                }
            }
        }
    }
}
