package com.binancebot.mobile.presentation.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.presentation.theme.*

@Composable
fun StatusBadge(
    status: String,
    modifier: Modifier = Modifier
) {
    val (backgroundColor, textColor, displayText) = when (status.lowercase()) {
        "running" -> Triple(
            SuccessGreen.copy(alpha = 0.2f),
            SuccessGreen,
            "RUNNING"
        )
        "stopped" -> Triple(
            MaterialTheme.colorScheme.surfaceVariant,
            MaterialTheme.colorScheme.onSurfaceVariant,
            "STOPPED"
        )
        "stopped_by_risk" -> Triple(
            MaterialTheme.colorScheme.errorContainer,
            MaterialTheme.colorScheme.onErrorContainer,
            "STOPPED BY RISK"
        )
        "error" -> Triple(
            ErrorRed.copy(alpha = 0.2f),
            ErrorRed,
            "ERROR"
        )
        else -> Triple(
            MaterialTheme.colorScheme.surfaceVariant,
            MaterialTheme.colorScheme.onSurfaceVariant,
            status.replaceFirstChar { it.uppercase() }
        )
    }
    
    Surface(
        modifier = modifier.height(24.dp),
        shape = MaterialTheme.shapes.small,
        color = backgroundColor
    ) {
        Text(
            text = displayText,
            style = MaterialTheme.typography.labelSmall,
            color = textColor,
            modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny)
        )
    }
}




