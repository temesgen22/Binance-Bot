package com.binancebot.mobile.presentation.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Notifications

/**
 * Notification Badge Component
 * Shows unread notification count
 */
@Composable
fun NotificationBadge(
    unreadCount: Int,
    modifier: Modifier = Modifier
) {
    if (unreadCount > 0) {
        BadgedBox(
            badge = {
                Badge {
                    Text(
                        text = if (unreadCount > 99) "99+" else unreadCount.toString(),
                        style = MaterialTheme.typography.labelSmall
                    )
                }
            },
            modifier = modifier
        ) {
            Icon(
                imageVector = Icons.Default.Notifications,
                contentDescription = "Notifications",
                modifier = Modifier.size(24.dp)
            )
        }
    } else {
        Icon(
            imageVector = Icons.Default.Notifications,
            contentDescription = "Notifications",
            modifier = modifier.size(24.dp)
        )
    }
}

