package com.binancebot.mobile.presentation.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Article
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.automirrored.filled.TrendingUp
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.theme.Spacing

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NavigationDrawer(
    currentRoute: String?,
    onNavigate: (String) -> Unit,
    onClose: () -> Unit,
    onLogout: () -> Unit,
    modifier: Modifier = Modifier
) {
    ModalDrawerSheet(modifier = modifier) {
        Column(
            modifier = Modifier.fillMaxSize()
        ) {
            // Header
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(Spacing.Large),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = "Binance Bot",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(Spacing.Small))
                Text(
                    text = "Trading Platform",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            
            HorizontalDivider()
            
            // Navigation Items - Scrollable
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .verticalScroll(rememberScrollState())
                    .padding(vertical = Spacing.Small)
            ) {
                NavigationDrawerItem(
                    icon = { Icon(Icons.Default.Home, contentDescription = null) },
                    label = { Text(Screen.Home.title) },
                    selected = currentRoute == Screen.Home.route,
                    onClick = {
                        onNavigate(Screen.Home.route)
                        onClose()
                    },
                    modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                icon = { Icon(Icons.Default.Dashboard, contentDescription = null) },
                label = { Text(Screen.Dashboard.title) },
                selected = currentRoute == Screen.Dashboard.route,
                onClick = {
                    onNavigate(Screen.Dashboard.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                    icon = { Icon(Icons.AutoMirrored.Filled.List, contentDescription = null) },
                label = { Text(Screen.Strategies.title) },
                selected = currentRoute == Screen.Strategies.route,
                onClick = {
                    onNavigate(Screen.Strategies.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                icon = { Icon(Icons.Default.ShoppingCart, contentDescription = null) },
                label = { Text(Screen.Trades.title) },
                selected = currentRoute == Screen.Trades.route,
                onClick = {
                    onNavigate(Screen.Trades.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                icon = { Icon(Icons.Default.AccountCircle, contentDescription = null) },
                label = { Text(Screen.Accounts.title) },
                selected = currentRoute == Screen.Accounts.route,
                onClick = {
                    onNavigate(Screen.Accounts.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                icon = { Icon(Icons.Default.Security, contentDescription = null) },
                label = { Text(Screen.RiskManagement.title) },
                selected = currentRoute == Screen.RiskManagement.route,
                onClick = {
                    onNavigate(Screen.RiskManagement.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                icon = { Icon(Icons.Default.Assessment, contentDescription = null) },
                label = { Text(Screen.Reports.title) },
                selected = currentRoute == Screen.Reports.route,
                onClick = {
                    onNavigate(Screen.Reports.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                    icon = { Icon(Icons.AutoMirrored.Filled.Article, contentDescription = null) },
                label = { Text(Screen.Logs.title) },
                selected = currentRoute == Screen.Logs.route,
                onClick = {
                    onNavigate(Screen.Logs.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                    icon = { Icon(Icons.AutoMirrored.Filled.TrendingUp, contentDescription = null) },
                    label = { Text(Screen.MarketAnalyzer.title) },
                selected = currentRoute == Screen.MarketAnalyzer.route,
                onClick = {
                    onNavigate(Screen.MarketAnalyzer.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                icon = { Icon(Icons.Default.Analytics, contentDescription = null) },
                label = { Text(Screen.Backtesting.title) },
                selected = currentRoute == Screen.Backtesting.route,
                onClick = {
                    onNavigate(Screen.Backtesting.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                    icon = { Icon(Icons.AutoMirrored.Filled.TrendingUp, contentDescription = null) },
                    label = { Text(Screen.WalkForward.title) },
                selected = currentRoute == Screen.WalkForward.route,
                onClick = {
                    onNavigate(Screen.WalkForward.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                icon = { Icon(Icons.Default.Assessment, contentDescription = null) },
                label = { Text(Screen.StrategyPerformance.title) },
                selected = currentRoute == Screen.StrategyPerformance.route,
                onClick = {
                    onNavigate(Screen.StrategyPerformance.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                icon = { Icon(Icons.Default.Security, contentDescription = null) },
                label = { Text(Screen.TestAccounts.title) },
                selected = currentRoute == Screen.TestAccounts.route,
                onClick = {
                    onNavigate(Screen.TestAccounts.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                icon = { Icon(Icons.Default.Tune, contentDescription = null) },
                label = { Text(Screen.AutoTuning.title) },
                selected = currentRoute == Screen.AutoTuning.route,
                onClick = {
                    onNavigate(Screen.AutoTuning.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
            )
                
                NavigationDrawerItem(
                    icon = { Icon(Icons.Default.NotificationsActive, contentDescription = null) },
                    label = { Text(Screen.PriceAlerts.title) },
                    selected = currentRoute == Screen.PriceAlerts.route,
                    onClick = {
                        onNavigate(Screen.PriceAlerts.route)
                        onClose()
                    },
                    modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                Divider(modifier = Modifier.padding(vertical = Spacing.Small))
                
                NavigationDrawerItem(
                icon = { Icon(Icons.Default.Settings, contentDescription = null) },
                label = { Text(Screen.Settings.title) },
                selected = currentRoute == Screen.Settings.route,
                onClick = {
                    onNavigate(Screen.Settings.route)
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
                
                NavigationDrawerItem(
                    icon = { Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = null) },
                label = { Text("Logout") },
                selected = false,
                onClick = {
                    onLogout()
                    onClose()
                },
                modifier = Modifier.padding(horizontal = Spacing.Small)
                )
            }
        }
    }
}


