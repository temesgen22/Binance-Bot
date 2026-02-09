package com.binancebot.mobile.presentation.screens.home

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
import androidx.navigation.NavController
import kotlinx.coroutines.launch
import com.binancebot.mobile.presentation.components.NavigationDrawer
import com.binancebot.mobile.presentation.components.BottomNavigationBar
import com.binancebot.mobile.presentation.components.shouldShowBottomNav
import com.binancebot.mobile.presentation.components.StatusBadge
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.util.FormatUtils
import com.binancebot.mobile.presentation.viewmodel.AuthViewModel
import com.binancebot.mobile.presentation.viewmodel.DashboardViewModel
import com.binancebot.mobile.presentation.viewmodel.DashboardUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    navController: NavController,
    authViewModel: AuthViewModel = hiltViewModel(),
    dashboardViewModel: DashboardViewModel = hiltViewModel(),
    strategiesViewModel: com.binancebot.mobile.presentation.viewmodel.StrategiesViewModel = hiltViewModel()
) {
    var drawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val currentRoute = navController.currentDestination?.route
    
    val strategies by dashboardViewModel.strategies.collectAsState()
    val uiState by dashboardViewModel.uiState.collectAsState()
    val totalStrategies = dashboardViewModel.totalStrategies
    val activeStrategies = dashboardViewModel.activeStrategies
    val totalUnrealizedPnL = dashboardViewModel.totalUnrealizedPnL
    
    // Calculate additional stats (using available data)
    // Note: These are approximations until strategy stats API is integrated
    val totalTrades = remember(strategies) {
        // For now, show count of strategies with positions as approximation
        // TODO: Get actual total trades from strategy stats API
        strategies.count { it.hasPosition } * 10 // Placeholder calculation
    }
    val winRate = remember(strategies) {
        // For now, calculate based on PnL (positive PnL = winning)
        // TODO: Get actual win rate from strategy stats API
        val strategiesWithPnL = strategies.filter { it.unrealizedPnL != null }
        if (strategiesWithPnL.isEmpty()) {
            0.0
        } else {
            val winningCount = strategiesWithPnL.count { (it.unrealizedPnL ?: 0.0) > 0 }
            (winningCount.toDouble() / strategiesWithPnL.size) * 100
        }
    }
    
    // Get recent strategies (last 5)
    val recentStrategies = remember(strategies) {
        strategies.take(5)
    }
    
    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            NavigationDrawer(
                currentRoute = currentRoute,
                onNavigate = { route ->
                    navController.navigate(route) {
                        if (currentRoute != Screen.Home.route) {
                            popUpTo(Screen.Home.route) {
                                inclusive = false
                            }
                        }
                    }
                },
                onClose = { scope.launch { drawerState.close() } },
                onLogout = {
                    authViewModel.logout()
                    navController.navigate(Screen.Login.route) {
                        popUpTo(0)
                    }
                }
            )
        }
    ) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text("Binance Bot") },
                    navigationIcon = {
                        IconButton(onClick = { scope.launch { drawerState.open() } }) {
                            Icon(Icons.Default.Menu, contentDescription = "Menu")
                        }
                    }
                )
            },
            bottomBar = {
                if (shouldShowBottomNav(currentRoute)) {
                    BottomNavigationBar(
                        currentRoute = currentRoute,
                        onNavigate = { route ->
                            navController.navigate(route) {
                                popUpTo(Screen.Home.route) { inclusive = false }
                                launchSingleTop = true
                            }
                        }
                    )
                }
            }
        ) { padding ->
            when (uiState) {
                is DashboardUiState.Loading -> {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator()
                    }
                }
                is DashboardUiState.Error -> {
                    ErrorHandler(
                        message = (uiState as DashboardUiState.Error).message,
                        onRetry = { dashboardViewModel.loadDashboardData() },
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding)
                    )
                }
                else -> {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(padding)
                            .padding(Spacing.ScreenPadding),
                        verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                    ) {
                        // Quick Stats Cards (2x2 Grid)
                        item {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                            ) {
                                QuickStatCard(
                                    title = "Total PnL",
                                    value = FormatUtils.formatCurrency(totalUnrealizedPnL),
                                    modifier = Modifier.weight(1f)
                                )
                                QuickStatCard(
                                    title = "Win Rate",
                                    value = String.format("%.1f%%", winRate),
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }
                        
                        item {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                            ) {
                                QuickStatCard(
                                    title = "Active Strategies",
                                    value = activeStrategies.toString(),
                                    modifier = Modifier.weight(1f)
                                )
                                QuickStatCard(
                                    title = "Total Trades",
                                    value = totalTrades.toString(),
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }
                        
                        // PnL Chart Card (Placeholder)
                        item {
                            Card(
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Column(
                                    modifier = Modifier.padding(Spacing.Medium)
                                ) {
                                    Text(
                                        text = "📈 PnL Chart (Last 7 Days)",
                                        style = MaterialTheme.typography.titleMedium,
                                        fontWeight = FontWeight.Bold
                                    )
                                    Spacer(modifier = Modifier.height(Spacing.Small))
                                    Text(
                                        text = "Chart will be displayed here",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    // TODO: Add actual chart component
                                }
                            }
                        }
                        
                        // Quick Actions Section
                        item {
                            Text(
                                text = "Quick Actions",
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold
                            )
                        }
                        
                        item {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                            ) {
                                QuickActionButton(
                                    text = "➕ New\nStrategy",
                                    onClick = { navController.navigate("create_strategy") },
                                    modifier = Modifier.weight(1f)
                                )
                                QuickActionButton(
                                    text = "▶️ Start\nAll",
                                    onClick = { 
                                        strategiesViewModel.startAllStrategies()
                                    },
                                    modifier = Modifier.weight(1f)
                                )
                                QuickActionButton(
                                    text = "⏸️ Stop\nAll",
                                    onClick = { 
                                        strategiesViewModel.stopAllStrategies()
                                    },
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }
                        
                        // Recent Strategies Section
                        item {
                            Text(
                                text = "Recent Strategies",
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold
                            )
                        }
                        
                        if (recentStrategies.isEmpty()) {
                            item {
                                Card(
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Column(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(Spacing.Large),
                                        horizontalAlignment = Alignment.CenterHorizontally
                                    ) {
                                        Text(
                                            text = "No strategies yet",
                                            style = MaterialTheme.typography.bodyLarge,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                }
                            }
                        } else {
                            items(recentStrategies) { strategy ->
                                StrategyCard(
                                    strategy = strategy,
                                    onClick = {
                                        navController.navigate("strategy_details/${strategy.id}")
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

@Composable
private fun QuickStatCard(
    title: String,
    value: String,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
    ) {
        Column(
            modifier = Modifier.padding(Spacing.Medium),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(modifier = Modifier.height(Spacing.Small))
            Text(
                text = value,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
private fun QuickActionButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    OutlinedButton(
        onClick = onClick,
        modifier = modifier
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.bodySmall
        )
    }
}

@Composable
private fun StrategyCard(
    strategy: com.binancebot.mobile.domain.model.Strategy,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = strategy.name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(Spacing.Small))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    StatusBadge(
                        status = if (strategy.isRunning) "Running" else "Stopped"
                    )
                    Text(
                        text = "| PnL: ${FormatUtils.formatCurrency(strategy.unrealizedPnL ?: 0.0)}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            Icon(
                imageVector = Icons.Default.ChevronRight,
                contentDescription = "View Details",
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

