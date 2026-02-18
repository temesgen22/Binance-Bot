package com.binancebot.mobile.presentation.screens.risk

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.RiskManagementViewModel
import com.binancebot.mobile.presentation.viewmodel.RiskManagementUiState
// Configuration Tab - Lists all accounts with their configurations
@Composable
fun ConfigurationTab(
    riskConfig: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?,
    onRetry: () -> Unit,
    viewModel: RiskManagementViewModel,
    accountId: String?
) {
    val accountViewModel: com.binancebot.mobile.presentation.viewmodel.AccountViewModel = androidx.hilt.navigation.compose.hiltViewModel()
    val accounts by accountViewModel.accounts.collectAsState()
    val allAccountConfigs by viewModel.allAccountConfigs.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    
    var expandedAccountIds by remember { mutableStateOf<Set<String>>(emptySet()) }
    var showEditDialog by remember { mutableStateOf(false) }
    var editingAccountId by remember { mutableStateOf<String?>(null) }
    var editingConfig by remember { mutableStateOf<com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?>(null) }
    
    // Load all account configs when accounts are loaded
    LaunchedEffect(accounts) {
        if (accounts.isNotEmpty()) {
            val accountIds = accounts.map { it.accountId } + listOf("default")
            viewModel.loadAllAccountConfigs(accountIds)
        }
    }
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(Spacing.ScreenPadding),
        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
    ) {
        // Header with Create button
        Text(
            text = "Risk Configurations",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold
        )
        
        when (uiState) {
            is RiskManagementUiState.Loading -> {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
            is RiskManagementUiState.Error -> {
                ErrorHandler(
                    message = (uiState as RiskManagementUiState.Error).message,
                    onRetry = {
                        if (accounts.isNotEmpty()) {
                            val accountIds = accounts.map { it.accountId } + listOf("default")
                            viewModel.loadAllAccountConfigs(accountIds)
                        }
                    },
                    modifier = Modifier.fillMaxSize()
                )
            }
            else -> {
                if (accounts.isEmpty()) {
                    EmptyStateCard(message = "No accounts found. Please create an account first.")
                } else {
                    LazyColumn(
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        // Default account
                        item {
                            AccountConfigCard(
                                accountId = "default",
                                accountName = "Default Account",
                                isTestnet = false,
                                config = allAccountConfigs["default"],
                                isExpanded = expandedAccountIds.contains("default"),
                                onExpandedChange = { expanded ->
                                    expandedAccountIds = if (expanded) {
                                        expandedAccountIds + "default"
                                    } else {
                                        expandedAccountIds - "default"
                                    }
                                },
                                onEdit = {
                                    editingAccountId = "default"
                                    editingConfig = allAccountConfigs["default"]
                                    showEditDialog = true
                                },
                                onCreate = {
                                    editingAccountId = "default"
                                    editingConfig = null
                                    showEditDialog = true
                                }
                            )
                        }
                        
                        // All other accounts
                        items(accounts.size) { index ->
                            val account = accounts[index]
                            AccountConfigCard(
                                accountId = account.accountId,
                                accountName = account.name ?: account.accountId,
                                isTestnet = account.testnet,
                                config = allAccountConfigs[account.accountId],
                                isExpanded = expandedAccountIds.contains(account.accountId),
                                onExpandedChange = { expanded ->
                                    expandedAccountIds = if (expanded) {
                                        expandedAccountIds + account.accountId
                                    } else {
                                        expandedAccountIds - account.accountId
                                    }
                                },
                                onEdit = {
                                    editingAccountId = account.accountId
                                    editingConfig = allAccountConfigs[account.accountId]
                                    showEditDialog = true
                                },
                                onCreate = {
                                    editingAccountId = account.accountId
                                    editingConfig = null
                                    showEditDialog = true
                                }
                            )
                        }
                    }
                }
            }
        }
    }
    
    // Show loading/error states for edit/create
    when (uiState) {
        is RiskManagementUiState.Success -> {
            LaunchedEffect(Unit) {
                if (showEditDialog) {
                    // Reload configs after save
                    if (accounts.isNotEmpty()) {
                        val accountIds = accounts.map { it.accountId } + listOf("default")
                        viewModel.loadAllAccountConfigs(accountIds)
                    }
                    showEditDialog = false
                }
            }
        }
        else -> {}
    }
    
    // Edit/Create Configuration Dialog
    if (showEditDialog) {
        EditRiskConfigDialog(
            config = editingConfig,
            isEdit = editingConfig != null,
            isLoading = uiState is RiskManagementUiState.Loading,
            errorMessage = (uiState as? RiskManagementUiState.Error)?.message,
            onDismiss = { 
                showEditDialog = false
                editingAccountId = null
                editingConfig = null
            },
            onSave = { updatedConfig ->
                if (editingConfig != null) {
                    viewModel.updateRiskConfig(editingAccountId, updatedConfig)
                } else {
                    viewModel.createRiskConfig(editingAccountId, updatedConfig)
                }
            },
            defaultAccountId = editingAccountId
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AccountConfigCard(
    accountId: String,
    accountName: String,
    isTestnet: Boolean,
    config: com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto?,
    isExpanded: Boolean,
    onExpandedChange: (Boolean) -> Unit,
    onEdit: () -> Unit,
    onCreate: () -> Unit
) {
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
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .clickable { onExpandedChange(!isExpanded) }
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                    ) {
                        Text(
                            text = accountName,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        if (isTestnet) {
                            Surface(
                                shape = MaterialTheme.shapes.small,
                                color = MaterialTheme.colorScheme.secondaryContainer
                            ) {
                                Text(
                                    text = "Testnet",
                                    modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSecondaryContainer
                                )
                            }
                        }
                    }
                    Text(
                        text = "Account ID: $accountId",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    if (config != null) {
                        IconButton(
                            onClick = { onEdit() },
                            modifier = Modifier.size(40.dp)
                        ) {
                            Icon(
                                Icons.Filled.Edit,
                                contentDescription = "Edit",
                                modifier = Modifier.size(20.dp)
                            )
                        }
                    } else {
                        Button(
                            onClick = { onCreate() },
                            modifier = Modifier.height(36.dp)
                        ) {
                            Icon(Icons.Filled.Add, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(Spacing.Tiny))
                            Text("Create", style = MaterialTheme.typography.labelSmall)
                        }
                    }
                    
                    IconButton(
                        onClick = { onExpandedChange(!isExpanded) },
                        modifier = Modifier.size(40.dp)
                    ) {
                        Icon(
                            if (isExpanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore,
                            contentDescription = if (isExpanded) "Collapse" else "Expand"
                        )
                    }
                }
            }
            
            // Status indicator
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(
                    shape = MaterialTheme.shapes.small,
                    color = if (config != null) {
                        MaterialTheme.colorScheme.primaryContainer
                    } else {
                        MaterialTheme.colorScheme.surfaceVariant
                    }
                ) {
                    Text(
                        text = if (config != null) "Configured" else "Not Configured",
                        modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                        style = MaterialTheme.typography.labelSmall,
                        color = if (config != null) {
                            MaterialTheme.colorScheme.onPrimaryContainer
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                        fontWeight = FontWeight.Bold
                    )
                }
            }
            
            // Expanded details (hidden by default)
            if (isExpanded && config != null) {
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                
                // Portfolio Limits Summary
                Column(
                    verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
                ) {
                    Text(
                        text = "Portfolio Limits",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary
                    )
                    config.maxPortfolioExposureUsdt?.let {
                        Text(
                            text = "- Max Exposure: ${FormatUtils.formatCurrency(it)}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    config.maxDailyLossUsdt?.let {
                        Text(
                            text = "- Max Daily Loss: ${FormatUtils.formatCurrency(it)}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    config.maxWeeklyLossUsdt?.let {
                        Text(
                            text = "- Max Weekly Loss: ${FormatUtils.formatCurrency(it)}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    config.maxDrawdownPct?.let {
                        Text(
                            text = "- Max Drawdown: ${String.format("%.2f", it * 100)}%",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
                
                // Circuit Breaker Summary
                if (config.circuitBreakerEnabled) {
                    HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                    Column(
                        verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
                    ) {
                        Text(
                            text = "Circuit Breaker",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary
                        )
                        Text(
                            text = "- Enabled: Yes",
                            style = MaterialTheme.typography.bodySmall
                        )
                        config.maxConsecutiveLosses?.let {
                            Text(
                                text = "- Max Consecutive Losses: $it",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                }
                
                // Advanced Settings Summary
                val advancedEnabled = listOf(
                    config.volatilityBasedSizingEnabled to "Volatility-Based Sizing",
                    config.performanceBasedAdjustmentEnabled to "Performance-Based Adjustment",
                    config.kellyCriterionEnabled to "Kelly Criterion",
                    config.correlationLimitsEnabled to "Correlation Limits",
                    config.marginCallProtectionEnabled to "Margin Protection"
                ).filter { it.first }.map { it.second }
                
                if (advancedEnabled.isNotEmpty()) {
                    HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                    Column(
                        verticalArrangement = Arrangement.spacedBy(Spacing.Tiny)
                    ) {
                        Text(
                            text = "Advanced Settings",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary
                        )
                        advancedEnabled.forEach { setting ->
                            Text(
                                text = "- $setting: Enabled",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                }
            } else if (isExpanded && config == null) {
                HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Small))
                Text(
                    text = "No risk configuration found for this account. Click 'Create' to set up risk management.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun ConfigurationSection(
    title: String,
    items: List<String>
) {
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
                text = title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
            HorizontalDivider()
            items.forEach { item ->
                Text(
                    text = item,
                    style = MaterialTheme.typography.bodyMedium
                )
            }
        }
    }
}
