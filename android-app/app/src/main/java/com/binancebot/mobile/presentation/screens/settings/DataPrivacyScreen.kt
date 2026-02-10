package com.binancebot.mobile.presentation.screens.settings

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.binancebot.mobile.presentation.theme.Spacing

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DataPrivacyScreen(
    navController: NavController
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Data & Privacy") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(Spacing.ScreenPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            // Data Collection
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
                    Text(
                        text = "Data Collection",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    HorizontalDivider()
                    Text(
                        text = "We collect the following data:",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(Spacing.Small))
                    Text("• Account information (username, email)")
                    Text("• Trading data (strategies, trades, performance)")
                    Text("• API credentials (encrypted)")
                    Text("• App usage analytics")
                }
            }
            
            // Data Storage
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
                    Text(
                        text = "Data Storage",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    HorizontalDivider()
                    Text(
                        text = "Your data is stored securely:",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(Spacing.Small))
                    Text("• API credentials are encrypted")
                    Text("• Data is stored on secure servers")
                    Text("• Local data is encrypted")
                }
            }
            
            // Privacy Rights
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
                    Text(
                        text = "Your Privacy Rights",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    HorizontalDivider()
                    Text(
                        text = "You have the right to:",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(Spacing.Small))
                    Text("• Access your data")
                    Text("• Delete your account")
                    Text("• Export your data")
                    Text("• Opt out of analytics")
                }
            }
            
            // Actions
            Button(
                onClick = { /* TODO: Implement data export */ },
                modifier = Modifier.fillMaxWidth()
            ) {
                Icon(Icons.Default.FileDownload, null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text("Export My Data")
            }
            
            OutlinedButton(
                onClick = { /* TODO: Implement delete account */ },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.outlinedButtonColors(
                    contentColor = MaterialTheme.colorScheme.error
                )
            ) {
                Icon(Icons.Default.Delete, null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text("Delete Account")
            }
        }
    }
}



