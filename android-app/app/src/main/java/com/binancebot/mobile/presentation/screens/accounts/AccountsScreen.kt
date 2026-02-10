package com.binancebot.mobile.presentation.screens.accounts

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.presentation.components.ErrorHandler
import com.binancebot.mobile.presentation.components.BottomNavigationBar
import com.binancebot.mobile.presentation.components.shouldShowBottomNav
import com.binancebot.mobile.presentation.components.SwipeRefreshBox
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.screens.accounts.CreateAccountDialog
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.viewmodel.AccountViewModel
import com.binancebot.mobile.presentation.viewmodel.AccountUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountsScreen(
    navController: NavController,
    viewModel: AccountViewModel = hiltViewModel()
) {
    val accounts by viewModel.accounts.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    val currentRoute = navController.currentDestination?.route
    
    var showCreateDialog by remember { mutableStateOf(false) }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Accounts") },
                actions = {
                    IconButton(onClick = { viewModel.loadAccounts() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                }
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { showCreateDialog = true }
            ) {
                Icon(Icons.Default.Add, contentDescription = "Add Account")
            }
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
        // Create Account Dialog
        if (showCreateDialog) {
            CreateAccountDialog(
                onDismiss = { showCreateDialog = false },
                onCreate = { name, apiKey, apiSecret, testnet ->
                    viewModel.createAccount(name, apiKey, apiSecret, testnet)
                    showCreateDialog = false
                }
            )
        }
        
        when (uiState) {
            is AccountUiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
            is AccountUiState.Error -> {
                ErrorHandler(
                    message = (uiState as AccountUiState.Error).message,
                    onRetry = { viewModel.loadAccounts() },
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                )
            }
            else -> {
                SwipeRefreshBox(
                    isRefreshing = uiState is AccountUiState.Loading,
                    onRefresh = { viewModel.loadAccounts() }
                ) {
                    if (accounts.isEmpty()) {
                        Box(
                            modifier = Modifier
                                .fillMaxSize()
                                .padding(padding),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(
                                horizontalAlignment = Alignment.CenterHorizontally
                            ) {
                                Text(
                                    text = "No accounts found",
                                    style = MaterialTheme.typography.titleMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Spacer(modifier = Modifier.height(Spacing.Small))
                                Text(
                                    text = "Add a Binance account to start trading",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    } else {
                        LazyColumn(
                            modifier = Modifier
                                .fillMaxSize()
                                .padding(padding),
                            contentPadding = PaddingValues(Spacing.ScreenPadding),
                            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
                        ) {
                            items(
                                items = accounts,
                                key = { it.accountId }
                            ) { account ->
                                AccountCard(account = account)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun AccountCard(account: com.binancebot.mobile.domain.model.Account) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.CardPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Small)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = account.name ?: account.accountId,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = account.accountId,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    if (account.isDefault) {
                        Surface(
                            shape = MaterialTheme.shapes.small,
                            color = MaterialTheme.colorScheme.primaryContainer
                        ) {
                            Text(
                                text = "Default",
                                modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer
                            )
                        }
                    }
                    if (account.testnet) {
                        Surface(
                            shape = MaterialTheme.shapes.small,
                            color = MaterialTheme.colorScheme.secondaryContainer
                        ) {
                            Text(
                                text = "Testnet",
                                modifier = Modifier.padding(horizontal = Spacing.Small, vertical = Spacing.Tiny),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSecondaryContainer
                            )
                        }
                    }
                }
            }
            
            HorizontalDivider()
            
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text(
                        text = "Platform",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = account.exchangePlatform,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
                Column {
                    Text(
                        text = "Status",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = if (account.isActive) "Active" else "Inactive",
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (account.isActive) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        }
                    )
                }
                account.paperBalance?.let { balance ->
                    Column {
                        Text(
                            text = "Paper Balance",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "${String.format("%.2f", balance)} USDT",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }
    }
}
