@file:OptIn(ExperimentalMaterial3Api::class)

package com.binancebot.mobile.presentation.screens.trades

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.presentation.components.BottomNavigationBar
import com.binancebot.mobile.presentation.components.OfflineIndicator
import com.binancebot.mobile.presentation.components.shouldShowBottomNav
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.viewmodel.TradesViewModel

@Composable
fun TradesScreen(
    navController: NavController,
    viewModel: TradesViewModel = hiltViewModel()
) {
    val currentRoute = navController.currentDestination?.route
    val allOpenPositions by viewModel.allOpenPositions.collectAsState()
    val pnlLoading by viewModel.pnlLoading.collectAsState()
    val isOnline = remember { mutableStateOf(true) }
    val lastSyncTime = remember { mutableStateOf<Long?>(null) }

    LaunchedEffect(Unit) {
        viewModel.loadPnLOverview()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Open Positions") },
                actions = {
                    IconButton(onClick = { viewModel.loadPnLOverview() }) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh"
                        )
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
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            OfflineIndicator(
                isOnline = isOnline.value,
                lastSyncTime = lastSyncTime.value,
                modifier = Modifier.fillMaxWidth()
            )

            PositionsTab(
                positions = allOpenPositions,
                isLoading = pnlLoading,
                onRefresh = { viewModel.loadPnLOverview() },
                onStrategyClick = { strategyId ->
                    navController.navigate("strategy_details/$strategyId")
                },
                modifier = Modifier.fillMaxSize()
            )
        }
    }
}
