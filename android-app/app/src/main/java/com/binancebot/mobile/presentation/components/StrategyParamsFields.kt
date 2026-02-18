package com.binancebot.mobile.presentation.components

import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.BacktestStrategyDefaults

/**
 * Renders strategy parameter fields from definitions (same as web app strategyParams).
 * When strategy type is selected, show labeled inputs for each param and call onValueChange when user edits.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StrategyParamsFields(
    paramDefs: List<BacktestStrategyDefaults.ParamDef>,
    values: Map<String, Any>,
    onValueChange: (String, Any) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true
) {
    Column(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
    ) {
        paramDefs.forEach { def ->
            when (def) {
                is BacktestStrategyDefaults.ParamDef.Number -> {
                    val current = (values[def.key] as? Number)?.toDouble() ?: def.value
                    OutlinedTextField(
                        value = current.toString(),
                        onValueChange = { s ->
                            s.toDoubleOrNull()?.coerceIn(def.min, def.max)?.let { onValueChange(def.key, it) }
                        },
                        label = { Text(def.label) },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        enabled = enabled
                    )
                }
                is BacktestStrategyDefaults.ParamDef.Int -> {
                    val current = (values[def.key] as? Number)?.toInt() ?: def.value
                    OutlinedTextField(
                        value = current.toString(),
                        onValueChange = { s ->
                            s.toIntOrNull()?.coerceIn(def.min, def.max)?.let { onValueChange(def.key, it) }
                        },
                        label = { Text(def.label) },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        enabled = enabled
                    )
                }
                is BacktestStrategyDefaults.ParamDef.Checkbox -> {
                    val current = values[def.key] as? Boolean ?: def.value
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(def.label, style = MaterialTheme.typography.bodyMedium)
                        Switch(
                            checked = current,
                            onCheckedChange = { onValueChange(def.key, it) },
                            enabled = enabled
                        )
                    }
                }
                is BacktestStrategyDefaults.ParamDef.Select -> {
                    val current = values[def.key] as? String ?: def.value
                    var expanded by remember { mutableStateOf(false) }
                    ExposedDropdownMenuBox(
                        expanded = expanded,
                        onExpandedChange = { expanded = it }
                    ) {
                        OutlinedTextField(
                            value = current,
                            onValueChange = {},
                            readOnly = true,
                            label = { Text(def.label) },
                            modifier = Modifier.fillMaxWidth().menuAnchor(),
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
                            enabled = enabled
                        )
                        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                            def.options.forEach { opt ->
                                DropdownMenuItem(
                                    text = { Text(opt) },
                                    onClick = {
                                        onValueChange(def.key, opt)
                                        expanded = false
                                    }
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
