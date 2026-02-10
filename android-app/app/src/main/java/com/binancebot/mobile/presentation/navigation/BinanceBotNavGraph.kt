package com.binancebot.mobile.presentation.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import com.binancebot.mobile.presentation.screens.accounts.AccountsScreen
import com.binancebot.mobile.presentation.screens.auth.LoginScreen
import com.binancebot.mobile.presentation.screens.auth.RegisterScreen
import com.binancebot.mobile.presentation.screens.dashboard.DashboardScreen
import com.binancebot.mobile.presentation.screens.home.HomeScreen
import com.binancebot.mobile.presentation.screens.logs.LogsScreen
import com.binancebot.mobile.presentation.screens.reports.ReportsScreen
import com.binancebot.mobile.presentation.screens.risk.RiskManagementScreen
import com.binancebot.mobile.presentation.screens.settings.SettingsScreen
import com.binancebot.mobile.presentation.screens.strategies.StrategiesScreen
import com.binancebot.mobile.presentation.screens.trades.TradesScreen
import com.binancebot.mobile.presentation.screens.marketanalyzer.MarketAnalyzerScreen
import com.binancebot.mobile.presentation.navigation.Screen

@Composable
fun BinanceBotNavGraph(
    navController: NavHostController,
    startDestination: String,
    onOpenDrawer: () -> Unit = {}
) {
    // onOpenDrawer kept for potential future drawer navigation
    NavHost(navController = navController, startDestination = startDestination) {
        composable(Screen.Login.route) {
            LoginScreen(
                onLoginSuccess = {
                    navController.navigate(Screen.Home.route) {
                        popUpTo(0)
                    }
                },
                onNavigateToRegister = {
                    navController.navigate(Screen.Register.route)
                }
            )
        }
        composable(Screen.Register.route) {
            RegisterScreen(
                onRegisterSuccess = {
                    navController.navigate(Screen.Home.route) {
                        popUpTo(0)
                    }
                },
                onNavigateToLogin = {
                    navController.navigate(Screen.Login.route)
                }
            )
        }
        composable(Screen.Home.route) {
            HomeScreen(navController = navController)
        }
        composable(Screen.Dashboard.route) {
            DashboardScreen(navController = navController)
        }
        composable(Screen.Strategies.route) {
            StrategiesScreen(navController = navController)
        }
        composable("create_strategy") {
            com.binancebot.mobile.presentation.screens.strategies.CreateStrategyScreen(
                navController = navController
            )
        }
        composable("strategy_details/{strategyId}") { backStackEntry ->
            val strategyId = backStackEntry.arguments?.getString("strategyId") ?: ""
            com.binancebot.mobile.presentation.screens.strategies.StrategyDetailsScreen(
                strategyId = strategyId,
                navController = navController
            )
        }
        composable(Screen.Trades.route) {
            TradesScreen(navController = navController)
        }
        composable(Screen.Accounts.route) {
            AccountsScreen(navController = navController)
        }
        composable(Screen.Logs.route) {
            LogsScreen(navController = navController)
        }
        composable(Screen.Reports.route) {
            ReportsScreen(navController = navController)
        }
        composable(Screen.RiskManagement.route) {
            RiskManagementScreen(navController = navController)
        }
        composable(Screen.MarketAnalyzer.route) {
            MarketAnalyzerScreen(navController = navController)
        }
        composable(Screen.Backtesting.route) {
            com.binancebot.mobile.presentation.screens.backtesting.BacktestingScreen(navController = navController)
        }
        composable(Screen.WalkForward.route) {
            com.binancebot.mobile.presentation.screens.walkforward.WalkForwardScreen(navController = navController)
        }
        composable(Screen.StrategyPerformance.route) {
            com.binancebot.mobile.presentation.screens.performance.StrategyPerformanceScreen(
                navController = navController
            )
        }
        composable("strategy_comparison/{strategyIds}") { backStackEntry ->
            val strategyIds = backStackEntry.arguments?.getString("strategyIds")?.split(",") ?: emptyList()
            com.binancebot.mobile.presentation.screens.performance.StrategyComparisonScreen(
                strategyIds = strategyIds,
                navController = navController
            )
        }
        composable(Screen.TestAccounts.route) {
            com.binancebot.mobile.presentation.screens.testaccounts.TestAccountsScreen(navController = navController)
        }
        composable(Screen.AutoTuning.route) {
            com.binancebot.mobile.presentation.screens.autotuning.AutoTuningScreen(navController = navController)
        }
        composable(Screen.Settings.route) {
            SettingsScreen(navController = navController)
        }
        composable("help") {
            com.binancebot.mobile.presentation.screens.help.HelpScreen(navController = navController)
        }
        composable("data_privacy") {
            com.binancebot.mobile.presentation.screens.settings.DataPrivacyScreen(navController = navController)
        }
    }
}
