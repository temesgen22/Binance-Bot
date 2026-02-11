package com.binancebot.mobile.presentation

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.lifecycle.lifecycleScope
import androidx.navigation.compose.rememberNavController
import com.binancebot.mobile.presentation.navigation.BinanceBotNavGraph
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.theme.BinanceBotTheme
import com.binancebot.mobile.util.ConnectivityManager
import com.binancebot.mobile.util.PreferencesManager
import com.binancebot.mobile.util.SyncManager
import com.binancebot.mobile.util.TokenManager
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    
    @Inject
    lateinit var tokenManager: TokenManager
    
    @Inject
    lateinit var preferencesManager: PreferencesManager
    
    @Inject
    lateinit var connectivityManager: ConnectivityManager
    
    @Inject
    lateinit var syncManager: SyncManager
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Note: WebSocket connection disabled - backend doesn't have WebSocket server yet
        // The backend returns 404 for /ws endpoint, confirming no WebSocket server exists
        // 
        // Notifications will work via:
        // 1. FCM push notifications (when backend sends them)
        // 2. Polling-based detection (future enhancement)
        //
        // When backend implements WebSocket server, uncomment below:
        // @Inject lateinit var webSocketManager: com.binancebot.mobile.data.remote.websocket.WebSocketManager
        // @Inject lateinit var notificationTrigger: com.binancebot.mobile.util.NotificationTrigger
        // if (tokenManager.isLoggedIn()) {
        //     val baseUrl = com.binancebot.mobile.util.Constants.BASE_URL
        //     val wsUrl = baseUrl
        //         .replace("http://", "ws://")
        //         .replace("https://", "wss://")
        //         .replace("/api/", "/ws")
        //     webSocketManager.connect(wsUrl)
        //     notificationTrigger.startListening()
        // }
        
        // Handle deep link from notification
        handleDeepLink(intent)
        
        setContent {
            // Get theme mode from preferences
            val themeMode by preferencesManager.themeMode.collectAsState(initial = "auto")
            val isSystemInDarkTheme = androidx.compose.foundation.isSystemInDarkTheme()
            val darkTheme = when (themeMode) {
                "light" -> false
                "dark" -> true
                else -> isSystemInDarkTheme
            }
            
            BinanceBotTheme(darkTheme = darkTheme) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    BinanceBotApp(tokenManager = tokenManager)
                }
            }
        }
    }
    
    override fun onNewIntent(intent: android.content.Intent?) {
        super.onNewIntent(intent)
        intent?.let { handleDeepLink(it) }
    }
    
    private fun handleDeepLink(intent: android.content.Intent) {
        val deepLink = intent.getStringExtra("deep_link")
        val tradeId = intent.getStringExtra("trade_id")
        val strategyId = intent.getStringExtra("strategy_id")
        val notificationId = intent.getStringExtra("notification_id")
        
        // Deep link will be handled by navigation when app is running
        // Store in shared preferences or use a StateFlow for navigation
        if (deepLink != null || tradeId != null || strategyId != null) {
            // Navigation will be handled by BinanceBotNavGraph
            // This is a placeholder - actual navigation should be done via NavController
        }
    }
}

@Composable
fun BinanceBotApp(tokenManager: TokenManager) {
    val navController = rememberNavController()
    var startDestination by remember { mutableStateOf<String?>(null) }
    var isValidating by remember { mutableStateOf(true) }
    
    // Validate token on app start
    LaunchedEffect(Unit) {
        if (tokenManager.isLoggedIn()) {
            // Try to refresh token to validate it
            val refreshedToken = tokenManager.refreshToken()
            if (refreshedToken != null) {
                startDestination = Screen.Home.route
            } else {
                // Token is invalid, clear and go to login
                tokenManager.clearTokens()
                startDestination = Screen.Login.route
            }
        } else {
            startDestination = Screen.Login.route
        }
        isValidating = false
    }
    
    // Show loading while validating
    if (isValidating || startDestination == null) {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = MaterialTheme.colorScheme.background
        ) {
            // Could show a loading indicator here
        }
    } else {
        BinanceBotNavGraph(
            navController = navController,
            startDestination = startDestination!!
        )
    }
}
