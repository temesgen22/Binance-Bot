package com.binancebot.mobile.presentation.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
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
                        contentDescription = screen.title
                    )
                },
                label = { Text(screen.title) },
                selected = currentRoute == screen.route,
                onClick = { onNavigate(screen.route) }
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

