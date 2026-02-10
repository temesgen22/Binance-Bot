package com.binancebot.mobile.presentation.screens.help

import androidx.compose.foundation.clickable
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
fun HelpScreen(
    navController: NavController
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Help & Support") },
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
            // Getting Started
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
                        text = "Getting Started",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    HorizontalDivider()
                    HelpItem(
                        question = "How do I create a strategy?",
                        answer = "Go to Strategies screen, tap the + button, fill in the strategy details, and tap Create."
                    )
                    HelpItem(
                        question = "How do I add a Binance account?",
                        answer = "Go to Accounts screen, tap the + button, enter your API key and secret, then tap Add."
                    )
                    HelpItem(
                        question = "How do I start trading?",
                        answer = "Create a strategy, add a Binance account, then start the strategy from the Strategies screen."
                    )
                }
            }
            
            // Common Questions
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
                        text = "Common Questions",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    HorizontalDivider()
                    HelpItem(
                        question = "What is risk management?",
                        answer = "Risk management helps protect your portfolio by setting limits on exposure, losses, and drawdowns."
                    )
                    HelpItem(
                        question = "How does backtesting work?",
                        answer = "Backtesting allows you to test strategies on historical data to evaluate performance before live trading."
                    )
                    HelpItem(
                        question = "What is auto-tuning?",
                        answer = "Auto-tuning automatically optimizes strategy parameters based on market conditions to improve performance."
                    )
                }
            }
            
            // Trading Features
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
                        text = "Trading Features",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    HorizontalDivider()
                    HelpItem(
                        question = "How do I use Market Analyzer?",
                        answer = "Go to Market Analyzer, select a symbol and timeframe, then tap Analyze to get market insights, trend indicators, and trading recommendations."
                    )
                    HelpItem(
                        question = "How does Backtesting work?",
                        answer = "Select a strategy, choose date range and parameters, then run backtest to see how the strategy would have performed on historical data."
                    )
                    HelpItem(
                        question = "What is Walk-Forward Analysis?",
                        answer = "Walk-Forward Analysis tests strategies across multiple time periods to validate performance consistency and avoid overfitting."
                    )
                    HelpItem(
                        question = "How do I enable Auto-Tuning?",
                        answer = "Go to Auto-Tuning screen, select a strategy, and enable auto-tuning. The system will automatically optimize parameters based on market conditions."
                    )
                }
            }
            
            // Support
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
                        text = "Support",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    HorizontalDivider()
                    Text(
                        text = "For additional help, please contact support:",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(Spacing.Small))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Default.Email,
                            contentDescription = null,
                            modifier = Modifier.size(20.dp),
                            tint = MaterialTheme.colorScheme.primary
                        )
                        Spacer(modifier = Modifier.width(Spacing.Small))
                        Text(
                            text = "Email: support@binancebot.com",
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Default.Language,
                            contentDescription = null,
                            modifier = Modifier.size(20.dp),
                            tint = MaterialTheme.colorScheme.primary
                        )
                        Spacer(modifier = Modifier.width(Spacing.Small))
                        Text(
                            text = "Documentation: docs.binancebot.com",
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun HelpItem(
    question: String,
    answer: String
) {
    var expanded by remember { mutableStateOf(false) }
    
    Column(
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { expanded = !expanded },
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = question,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
                modifier = Modifier.weight(1f)
            )
            Icon(
                imageVector = if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                contentDescription = if (expanded) "Collapse" else "Expand"
            )
        }
        if (expanded) {
            Spacer(modifier = Modifier.height(Spacing.Small))
            Text(
                text = answer,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(start = Spacing.Medium)
            )
        }
    }
}

