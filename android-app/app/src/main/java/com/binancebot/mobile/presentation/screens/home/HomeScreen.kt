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
                                    text = "⚠️ Alerts & Warnings",
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
private fun RiskStatusBanner(
    riskStatus: String?,
    accountCount: Int,
    onClick: () -> Unit
) {
    val status = riskStatus?.lowercase() ?: "active"
    
    val bgColor: Color
    val textColor: Color
    val icon: androidx.compose.ui.graphics.vector.ImageVector
    val message: String
    
    when (status) {
        "breach", "paused" -> {
            bgColor = MaterialTheme.colorScheme.errorContainer
            textColor = MaterialTheme.colorScheme.onErrorContainer
            icon = Icons.Default.Warning
            message = if (accountCount > 0) "$accountCount account(s) in breach" else "Portfolio breach detected"
        }
        "warning" -> {
            bgColor = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.7f)
            textColor = MaterialTheme.colorScheme.onErrorContainer
            icon = Icons.Default.Warning
            message = if (accountCount > 0) "$accountCount account(s) in warning" else "Portfolio warning"
        }
        else -> return // Don't show banner if status is active/normal
    }
    
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = bgColor)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.Medium),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Medium),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = textColor,
                modifier = Modifier.size(24.dp)
            )
            Text(
                text = message,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = textColor,
                modifier = Modifier.weight(1f)
            )
            Icon(
                imageVector = Icons.Default.ChevronRight,
                contentDescription = "View Details",
                tint = textColor
            )
        }
    }
}

@Composable
private fun TotalPnLHeroCard(
    totalPnL: Double,
    realizedPnL: Double,
    unrealizedPnL: Double,
    pnlChange24h: Double?
) {
    val isPositive = totalPnL >= 0
    val gradientColors = if (isPositive) {
        listOf(
            androidx.compose.ui.graphics.Color(0xFF4CAF50),
            androidx.compose.ui.graphics.Color(0xFF66BB6A)
        )
    } else {
        listOf(
            androidx.compose.ui.graphics.Color(0xFFF44336),
            androidx.compose.ui.graphics.Color(0xFFE57373)
        )
    }
    
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.large
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    brush = androidx.compose.ui.graphics.Brush.horizontalGradient(gradientColors)
                )
                .padding(Spacing.Large)
        ) {
            Column(
                verticalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                Text(
                    text = "Total PnL",
                    style = MaterialTheme.typography.titleMedium,
                    color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.9f)
                )
                Text(
                    text = FormatUtils.formatCurrency(totalPnL),
                    style = MaterialTheme.typography.displaySmall,
                    fontWeight = FontWeight.Bold,
                    color = androidx.compose.ui.graphics.Color.White
                )
                if (pnlChange24h != null) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(Spacing.Tiny),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = if (pnlChange24h >= 0) Icons.Default.TrendingUp else Icons.Default.TrendingDown,
                            contentDescription = null,
                            tint = androidx.compose.ui.graphics.Color.White,
                            modifier = Modifier.size(16.dp)
                        )
                        Text(
                            text = "${if (pnlChange24h >= 0) "+" else ""}${FormatUtils.formatCurrency(pnlChange24h)} (24h)",
                            style = MaterialTheme.typography.bodyMedium,
                            color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.9f)
                        )
                    }
                }
                Row(
                    modifier = Modifier.padding(top = Spacing.Small),
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Medium)
                ) {
                    Column {
                        Text(
                            text = "Realized",
                            style = MaterialTheme.typography.bodySmall,
                            color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.8f)
                        )
                        Text(
                            text = FormatUtils.formatCurrency(realizedPnL),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            color = androidx.compose.ui.graphics.Color.White
                        )
                    }
                    Column {
                        Text(
                            text = "Unrealized",
                            style = MaterialTheme.typography.bodySmall,
                            color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.8f)
                        )
                        Text(
                            text = FormatUtils.formatCurrency(unrealizedPnL),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            color = androidx.compose.ui.graphics.Color.White
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun KeyMetricsGrid(
    totalPnL: Double,
    winRate: Double,
    totalTrades: Int,
    activeStrategies: Int,
    accountBalance: Double?,
    profitFactor: Double?
) {
    Column(
        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
    ) {
        // Row 1
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            MetricCard(
                title = "Total PnL",
                value = FormatUtils.formatCurrency(totalPnL),
                icon = Icons.Default.AccountBalance,
                isPositive = totalPnL >= 0,
                modifier = Modifier.weight(1f)
            )
            MetricCard(
                title = "Win Rate",
                value = String.format("%.1f%%", if (winRate > 1.0) winRate else winRate * 100),
                icon = Icons.Default.CheckCircle,
                modifier = Modifier.weight(1f)
            )
        }
        // Row 2
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            MetricCard(
                title = "Total Trades",
                value = totalTrades.toString(),
                icon = Icons.Default.SwapHoriz,
                modifier = Modifier.weight(1f)
            )
            MetricCard(
                title = "Active",
                value = activeStrategies.toString(),
                icon = Icons.Default.PlayArrow,
                modifier = Modifier.weight(1f)
            )
        }
        // Row 3
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            accountBalance?.let {
                MetricCard(
                    title = "Balance",
                    value = FormatUtils.formatCurrency(it),
                    icon = Icons.Default.AccountBalanceWallet,
                    modifier = Modifier.weight(1f)
                )
            }
            profitFactor?.let {
                MetricCard(
                    title = "Profit Factor",
                    value = String.format("%.2f", it),
                    icon = Icons.Default.Star,
                    modifier = Modifier.weight(1f)
                )
            }
        }
    }
}

@Composable
private fun MetricCard(
    title: String,
    value: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    modifier: Modifier = Modifier,
    isPositive: Boolean? = null
) {
    Card(modifier = modifier) {
        Column(
            modifier = Modifier.padding(Spacing.Medium),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = if (isPositive != null) {
                    if (isPositive) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                },
                modifier = Modifier.size(24.dp)
            )
            Spacer(modifier = Modifier.height(Spacing.Small))
            Text(
                text = title,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                text = value,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = if (isPositive != null) {
                    if (isPositive) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.onSurface
                }
            )
        }
    }
}

@Composable
private fun AccountRiskAlertsCard(
    accounts: List<com.binancebot.mobile.domain.model.Account>,
    riskStatus: com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto?,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f)
        )
    ) {
        Column(
            modifier = Modifier.padding(Spacing.Medium),
            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Default.Warning,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.error,
                    modifier = Modifier.size(20.dp)
                )
                Text(
                    text = "Account Risk Alerts",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.error
                )
            }
            riskStatus?.status?.let { status ->
                Text(
                    text = "Status: ${status.uppercase()}",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold
                )
            }
            riskStatus?.warnings?.forEach { warning ->
                Text(
                    text = "• $warning",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Text(
                text = "Tap to view details →",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(top = Spacing.Small)
            )
        }
    }
}

@Composable
private fun StrategyHealthAlertsCard(
    strategies: List<com.binancebot.mobile.domain.model.Strategy>,
    strategyHealth: Map<String, com.binancebot.mobile.data.remote.dto.StrategyHealthDto?>,
    onClick: (String) -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f)
        )
    ) {
        Column(
            modifier = Modifier.padding(Spacing.Medium),
            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Default.Warning,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.error,
                    modifier = Modifier.size(20.dp)
                )
                Text(
                    text = "Strategy Health Issues (${strategies.size})",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.error
                )
            }
            strategies.take(3).forEach { strategy ->
                val health = strategyHealth[strategy.id]
                val healthStatus = health?.healthStatus
                val statusText = when (healthStatus) {
                    "execution_stale" -> "Stale"
                    "task_dead" -> "Dead"
                    "no_recent_orders" -> "No Orders"
                    else -> "Issue"
                }
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onClick(strategy.id) },
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = strategy.name,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                        Text(
                            text = "${strategy.symbol} • $statusText",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Icon(
                        imageVector = Icons.Default.ChevronRight,
                        contentDescription = "View Details",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                if (strategy != strategies.take(3).last()) {
                    HorizontalDivider(modifier = Modifier.padding(vertical = Spacing.Tiny))
                }
            }
            if (strategies.size > 3) {
                Text(
                    text = "And ${strategies.size - 3} more...",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = Spacing.Small)
                )
            }
        }
    }
}

@Composable
private fun PnLChartSection(
    pnlTimeline: List<Map<String, Any>>?,
    totalPnL: Double
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(Spacing.Medium),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "PnL Timeline",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                // Time period selector would go here
            }
            
            if (pnlTimeline.isNullOrEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(200.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                    ) {
                        Icon(
                            imageVector = Icons.Default.ShowChart,
                            contentDescription = null,
                            modifier = Modifier.size(48.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                        )
                        Text(
                            text = "Chart data not available",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "Total PnL: ${FormatUtils.formatCurrency(totalPnL)}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            } else {
                // TODO: Implement actual chart using chart library
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(200.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "Chart implementation pending",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

@Composable
private fun QuickStatsGrid(
    bestStrategy: com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto?,
    worstStrategy: com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto?,
    topSymbol: com.binancebot.mobile.data.remote.dto.SymbolPnLDto?,
    completedTrades: Int
) {
    Column(
        verticalArrangement = Arrangement.spacedBy(Spacing.Small)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            bestStrategy?.let {
                QuickStatCard(
                    title = "Best Strategy",
                    value = "${it.strategyName}\n${FormatUtils.formatCurrency(it.totalPnl)}",
                    modifier = Modifier.weight(1f)
                )
            }
            worstStrategy?.let {
                QuickStatCard(
                    title = "Worst Strategy",
                    value = "${it.strategyName}\n${FormatUtils.formatCurrency(it.totalPnl)}",
                    modifier = Modifier.weight(1f)
                )
            }
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            topSymbol?.let {
                QuickStatCard(
                    title = "Top Symbol",
                    value = "${it.symbol}\n${FormatUtils.formatCurrency(it.totalPnL)}",
                    modifier = Modifier.weight(1f)
                )
            }
            QuickStatCard(
                title = "Completed",
                value = completedTrades.toString(),
                modifier = Modifier.weight(1f)
            )
        }
    }
}

@Composable
private fun EnhancedStrategyCard(
    strategy: com.binancebot.mobile.domain.model.Strategy,
    strategyHealth: com.binancebot.mobile.data.remote.dto.StrategyHealthDto?,
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
                Spacer(modifier = Modifier.height(Spacing.Tiny))
                Text(
                    text = "${strategy.symbol} • ${strategy.strategyType}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(modifier = Modifier.height(Spacing.Small))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    StatusBadge(status = strategy.status)
                    // Health indicator
                    strategyHealth?.let { health ->
                        val healthStatus = health.healthStatus
                        if (healthStatus in listOf("execution_stale", "task_dead", "no_recent_orders")) {
                            val (icon, color) = when (healthStatus) {
                                "execution_stale" -> "⚠" to MaterialTheme.colorScheme.error
                                "task_dead" -> "✗" to MaterialTheme.colorScheme.error
                                "no_recent_orders" -> "⚠" to MaterialTheme.colorScheme.errorContainer
                                else -> "?" to MaterialTheme.colorScheme.onSurfaceVariant
                            }
                            Box(
                                modifier = Modifier.size(20.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = icon,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = color,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                    }
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


