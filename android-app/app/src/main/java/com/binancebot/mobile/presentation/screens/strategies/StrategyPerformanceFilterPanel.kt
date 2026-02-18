@file:OptIn(ExperimentalMaterial3Api::class)

package com.binancebot.mobile.presentation.screens.strategies

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.domain.model.Account
import com.binancebot.mobile.presentation.theme.Spacing

/**
 * Filter panel for Strategy Performance screen: status chips, advanced filters (symbol, account, rank, dates).
 * Extracted for maintainability (P1.2).
 */
@Composable
fun StrategyPerformanceFilterPanel(
    filterStatus: String?,
    onFilterStatusChange: (String?) -> Unit,
    filterAccount: String?,
    onFilterAccountChange: (String?) -> Unit,
    filterSymbol: String,
    onFilterSymbolChange: (String) -> Unit,
    rankBy: String,
    onRankByChange: (String) -> Unit,
    startDate: String?,
    onStartDateChange: (String?) -> Unit,
    endDate: String?,
    onEndDateChange: (String?) -> Unit,
    accounts: List<Account>,
    showAdvancedFilters: Boolean,
    onShowAdvancedFiltersChange: (Boolean) -> Unit,
    onClearFilters: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = Spacing.ScreenPadding)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            FilterChip(
                selected = filterStatus == null,
                onClick = { onFilterStatusChange(null) },
                label = { Text("All") }
            )
            FilterChip(
                selected = filterStatus == "running",
                onClick = { onFilterStatusChange(if (filterStatus == "running") null else "running") },
                label = { Text("Running") }
            )
            FilterChip(
                selected = filterStatus == "stopped",
                onClick = { onFilterStatusChange(if (filterStatus == "stopped") null else "stopped") },
                label = { Text("Stopped") }
            )
            FilterChip(
                selected = filterStatus == "stopped_by_risk",
                onClick = { onFilterStatusChange(if (filterStatus == "stopped_by_risk") null else "stopped_by_risk") },
                label = { Text("Stopped by Risk") }
            )
            FilterChip(
                selected = filterStatus == "error",
                onClick = { onFilterStatusChange(if (filterStatus == "error") null else "error") },
                label = { Text("Error") }
            )
        }
        Spacer(modifier = Modifier.height(Spacing.Small))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(text = "Advanced Filters", style = MaterialTheme.typography.titleSmall)
            IconButton(onClick = { onShowAdvancedFiltersChange(!showAdvancedFilters) }) {
                Icon(
                    if (showAdvancedFilters) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                    contentDescription = "Toggle Advanced Filters"
                )
            }
        }
        AnimatedVisibility(
            visible = showAdvancedFilters,
            enter = expandVertically(),
            exit = shrinkVertically()
        ) {
            Card(
                modifier = Modifier.fillMaxWidth().heightIn(max = 300.dp),
                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
            ) {
                Column(
                    modifier = Modifier
                        .verticalScroll(rememberScrollState())
                        .padding(Spacing.Small),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    OutlinedTextField(
                        value = filterSymbol,
                        onValueChange = onFilterSymbolChange,
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Symbol") },
                        singleLine = true
                    )
                    AccountFilterDropdown(
                        accounts = accounts,
                        selectedAccountId = filterAccount,
                        onAccountSelected = onFilterAccountChange
                    )
                    RankBySelector(
                        selectedRankBy = rankBy,
                        onRankBySelected = onRankByChange
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                    ) {
                        OutlinedTextField(
                            value = startDate ?: "",
                            onValueChange = { onStartDateChange(it.takeIf { s -> s.isNotBlank() }) },
                            modifier = Modifier.weight(1f),
                            label = { Text("Start") },
                            placeholder = { Text("YYYY-MM-DD") },
                            singleLine = true
                        )
                        OutlinedTextField(
                            value = endDate ?: "",
                            onValueChange = { onEndDateChange(it.takeIf { s -> s.isNotBlank() }) },
                            modifier = Modifier.weight(1f),
                            label = { Text("End") },
                            placeholder = { Text("YYYY-MM-DD") },
                            singleLine = true
                        )
                    }
                    TextButton(onClick = onClearFilters, modifier = Modifier.fillMaxWidth()) {
                        Text("Clear All Filters")
                    }
                }
            }
        }
        Spacer(modifier = Modifier.height(Spacing.Small))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountFilterDropdown(
    accounts: List<Account>,
    selectedAccountId: String?,
    onAccountSelected: (String?) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = accounts.find { it.accountId == selectedAccountId }?.name ?: "All Accounts",
            onValueChange = {},
            readOnly = true,
            modifier = Modifier.fillMaxWidth().menuAnchor(),
            label = { Text("Account") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) }
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            DropdownMenuItem(
                text = { Text("All Accounts") },
                onClick = { onAccountSelected(null); expanded = false }
            )
            accounts.forEach { account ->
                DropdownMenuItem(
                    text = {
                        Text("${account.name} (${account.accountId})${if (account.testnet) " [TESTNET]" else ""}")
                    },
                    onClick = { onAccountSelected(account.accountId); expanded = false }
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RankBySelector(
    selectedRankBy: String,
    onRankBySelected: (String) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    val rankOptions = listOf(
        "total_pnl" to "Total PnL",
        "win_rate" to "Win Rate",
        "completed_trades" to "Completed Trades",
        "realized_pnl" to "Realized PnL",
        "unrealized_pnl" to "Unrealized PnL"
    )
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = rankOptions.find { it.first == selectedRankBy }?.second ?: "Total PnL",
            onValueChange = {},
            readOnly = true,
            modifier = Modifier.fillMaxWidth().menuAnchor(),
            label = { Text("Rank By") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) }
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            rankOptions.forEach { (value, label) ->
                DropdownMenuItem(
                    text = { Text(label) },
                    onClick = { onRankBySelected(value); expanded = false }
                )
            }
        }
    }
}
