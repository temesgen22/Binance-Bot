package com.binancebot.mobile.presentation.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.ui.graphics.vector.ImageVector

/**
 * Navigation screens for the app
 */
sealed class Screen(
    val route: String,
    val title: String,
    val icon: ImageVector? = null
) {
    object Login : Screen("login", "Login")
    object Register : Screen("register", "Register")
    object Home : Screen("home", "Home", Icons.Default.Home)
    object Dashboard : Screen("dashboard", "Dashboard", Icons.Default.Dashboard)
    object Strategies : Screen("strategies", "Strategies", Icons.Default.List)
    object Trades : Screen("trades", "Trades", Icons.Default.ShoppingCart)
    object Accounts : Screen("accounts", "Accounts", Icons.Default.AccountCircle)
    object Logs : Screen("logs", "Logs", Icons.Default.Article)
    object Reports : Screen("reports", "Reports", Icons.Default.Assessment)
    object RiskManagement : Screen("risk", "Risk Management", Icons.Default.Security)
    object MarketAnalyzer : Screen("market_analyzer", "Market Analyzer", Icons.Default.TrendingUp)
    object Backtesting : Screen("backtesting", "Backtesting", Icons.Default.Analytics)
    object WalkForward : Screen("walk_forward", "Walk-Forward Analysis", Icons.Default.TrendingUp)
    object StrategyPerformance : Screen("strategy_performance", "Strategy Performance", Icons.Default.Assessment)
    object TestAccounts : Screen("test_accounts", "Test Accounts", Icons.Default.Security)
    object AutoTuning : Screen("auto_tuning", "Auto-Tuning", Icons.Default.Tune)
    object Settings : Screen("settings", "Settings", Icons.Default.Settings)
    object Notifications : Screen("notifications", "Notifications", Icons.Default.Notifications)
    object PriceAlerts : Screen("price_alerts", "Price Alerts", Icons.Default.NotificationsActive)
}


