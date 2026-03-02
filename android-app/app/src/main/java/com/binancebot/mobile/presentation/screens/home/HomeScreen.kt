package com.binancebot.mobile.presentation.screens.home

import androidx.compose.foundation.background
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
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
    strategiesViewModel: com.binancebot.mobile.presentation.viewmodel.StrategiesViewModel = hiltViewModel(),
    riskManagementViewModel: com.binancebot.mobile.presentation.viewmodel.RiskManagementViewModel = hiltViewModel(),
    accountViewModel: com.binancebot.mobile.presentation.viewmodel.AccountViewModel = hiltViewModel()
) {
    var drawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val currentRoute = navController.currentDestination?.route
    
    val strategies by dashboardViewModel.strategies.collectAsState()
    val dashboardOverview by dashboardViewModel.dashboardOverview.collectAsState()
    val uiState by dashboardViewModel.uiState.collectAsState()
    val accounts by accountViewModel.accounts.collectAsState()
    
    // Use real data from dashboard overview
    val totalPnL = dashboardViewModel.totalPnL
    val totalTrades = dashboardViewModel.totalTrades
    val winRate = dashboardViewModel.overallWinRate
    val totalStrategies = dashboardViewModel.totalStrategies
    val activeStrategies = dashboardViewModel.activeStrategies
    val completedTrades = dashboardViewModel.completedTrades
    val realizedPnL = dashboardViewModel.realizedPnL
    val unrealizedPnL = dashboardViewModel.totalUnrealizedPnL
    
    // Load risk status for all accounts
    val portfolioRiskStatus by riskManagementViewModel.portfolioRiskStatus.collectAsState()
    val strategyHealth by strategiesViewModel.strategyHealth.collectAsState()
    
    // Load risk status and strategy health when screen loads
    LaunchedEffect(Unit) {
        // Load risk status for all accounts
        accounts.forEach { account ->
            riskManagementViewModel.loadPortfolioRiskStatus(account.accountId)
        }
        // Load health for running strategies
        strategies.filter { it.isRunning }.forEach { strategy ->
            strategiesViewModel.loadStrategyHealth(strategy.id)
        }
    }
    
    // Collect accounts with warnings/breaches
    val accountsWithIssues = remember(accounts, portfolioRiskStatus) {
        accounts.filter { account ->
            // Check if account has risk issues
            // For now, we'll check the portfolio status
            // TODO: Load per-account risk status
            portfolioRiskStatus?.status?.lowercase() in listOf("warning", "breach", "paused")
        }
    }
    
    // Collect strategies with health issues
    val strategiesWithHealthIssues = remember(strategies, strategyHealth) {
        strategies.filter { strategy ->
            if (!strategy.isRunning) return@filter false
            val health = strategyHealth[strategy.id]
            val healthStatus = health?.healthStatus
            healthStatus in listOf("execution_stale", "task_dead", "no_recent_orders")
        }
    }
    
    // Get top active strategies
    val topActiveStrategies = remember(strategies) {
        strategies.filter { it.isRunning }
            .sortedByDescending { it.unrealizedPnL ?: 0.0 }
            .take(5)
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
                        // Risk Status Banner (if there are warnings/breaches)
                        if (accountsWithIssues.isNotEmpty() || portfolioRiskStatus?.status?.lowercase() in listOf("warning", "breach", "paused")) {
                            item {
                                RiskStatusBanner(
                                    riskStatus = portfolioRiskStatus?.status,
                                    accountCount = accountsWithIssues.size,
                                    onClick = { navController.navigate(Screen.RiskManagement.route) }
                                )
                            }
                        }
                        
                        // Hero Section - Total PnL Card
                        item {
                            TotalPnLHeroCard(
                                totalPnL = totalPnL,
                                realizedPnL = realizedPnL,
                                unrealizedPnL = unrealizedPnL,
                                pnlChange24h = dashboardOverview?.pnlChange24h
                            )
                        }
                        
                        // Key Metrics Grid (2x3)
                        item {
                            KeyMetricsGrid(
                                totalPnL = totalPnL,
                                winRate = winRate,
                                totalTrades = totalTrades,
                                activeStrategies = activeStrategies,
                                accountBalance = dashboardOverview?.accountBalance,
                                profitFactor = null // TODO: Get from portfolio metrics
                            )
                        }
                        
                        // Risk & Health Alerts Section
                        if (accountsWithIssues.isNotEmpty() || strategiesWithHealthIssues.isNotEmpty()) {
                            item {
                                Text(
                                    text = "Alerts & Warnings",
                                    style = MaterialTheme.typography.titleLarge,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                            
                            if (accountsWithIssues.isNotEmpty()) {
                                item {
                                    AccountRiskAlertsCard(
                                        accounts = accountsWithIssues,
                                        riskStatus = portfolioRiskStatus,
                                        onClick = { navController.navigate(Screen.RiskManagement.route) }
                                    )
                                }
                            }
                            
                            if (strategiesWithHealthIssues.isNotEmpty()) {
                                item {
                                    StrategyHealthAlertsCard(
                                        strategies = strategiesWithHealthIssues,
                                        strategyHealth = strategyHealth,
                                        onClick = { strategyId ->
                                            navController.navigate("strategy_details/$strategyId")
                                        }
                                    )
                                }
                            }
                        }
                        
                        // PnL Chart Section
                        item {
                            PnLChartSection(
                                pnlTimeline = dashboardOverview?.pnlTimeline,
                                totalPnL = totalPnL
                            )
                        }
                        
                        // Quick Stats (Best/Worst Strategy, Top Symbol)
                        dashboardOverview?.let { overview ->
                            item {
                                Text(
                                    text = "Performance Highlights",
                                    style = MaterialTheme.typography.titleLarge,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                            
                            item {
                                QuickStatsGrid(
                                    bestStrategy = overview.bestStrategy,
                                    worstStrategy = overview.worstStrategy,
                                    topSymbol = overview.topSymbol,
                                    completedTrades = completedTrades
                                )
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
                                    text = "New\nStrategy",
                                    onClick = { navController.navigate("create_strategy") },
                                    modifier = Modifier.weight(1f)
                                )
                                QuickActionButton(
                                    text = "Start\nAll",
                                    onClick = { 
                                        strategiesViewModel.startAllStrategies()
                                    },
                                    modifier = Modifier.weight(1f)
                                )
                                QuickActionButton(
                                    text = "Stop\nAll",
                                    onClick = { 
                                        strategiesViewModel.stopAllStrategies()
                                    },
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }
                        
                        // Active Strategies Preview
                        item {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "Active Strategies",
                                    style = MaterialTheme.typography.titleLarge,
                                    fontWeight = FontWeight.Bold
                                )
                                if (topActiveStrategies.size < strategies.count { it.isRunning }) {
                                    TextButton(
                                        onClick = { navController.navigate(Screen.Strategies.route) }
                                    ) {
                                        Text("View All")
                                    }
                                }
                            }
                        }
                        
                        if (topActiveStrategies.isEmpty()) {
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
                                            text = "No active strategies",
                                            style = MaterialTheme.typography.bodyLarge,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                }
                            }
                        } else {
                            items(topActiveStrategies) { strategy ->
                                EnhancedStrategyCard(
                                    strategy = strategy,
                                    strategyHealth = strategyHealth[strategy.id],
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
// QuickStatCard, QuickActionButton, RiskStatusBanner, TotalPnLHeroCard, KeyMetricsGrid, MetricCard,
// AccountRiskAlertsCard, StrategyHealthAlertsCard, PnLChartSection, QuickStatsGrid, EnhancedStrategyCard -> HomeCards.kt (P1.3)

