package com.binancebot.mobile.presentation.components

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.presentation.navigation.Screen

/**
 * Bottom Navigation Bar for Option 1 design
 * Shows 5 main navigation items: Home, Dashboard, Strategies, Trades, Accounts
 */
@Composable
fun BottomNavigationBar(
    currentRoute: String?,
    onNavigate: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val bottomNavItems = listOf(
        Screen.Home,
        Screen.Dashboard,
        Screen.Strategies,
        Screen.Trades,
        Screen.Accounts
    )

    NavigationBar(modifier = modifier) {
        bottomNavItems.forEach { screen ->
            NavigationBarItem(
                icon = {
                    Icon(
                        imageVector = screen.icon ?: Icons.Default.Home,
                        contentDescription = screen.title,
                        modifier = Modifier.size(24.dp)
                    )
                },
                label = {
                    Text(
                        text = screen.title,
                        style = MaterialTheme.typography.labelSmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                },
                selected = currentRoute == screen.route,
                onClick = { onNavigate(screen.route) },
                alwaysShowLabel = true
            )
        }
    }
}

/**
 * Helper function to determine if bottom navigation should be shown
 * Bottom nav should only appear on the 5 main screens
 */
fun shouldShowBottomNav(route: String?): Boolean {
    return route in listOf(
        Screen.Home.route,
        Screen.Dashboard.route,
        Screen.Strategies.route,
        Screen.Trades.route,
        Screen.Accounts.route
    )
}

