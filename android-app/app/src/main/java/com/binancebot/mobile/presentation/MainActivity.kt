package com.binancebot.mobile.presentation

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.navigation.compose.rememberNavController
import com.binancebot.mobile.data.remote.websocket.PositionUpdateStore
import com.binancebot.mobile.data.remote.websocket.UpdateMessage
import com.binancebot.mobile.data.remote.websocket.WebSocketManager
import com.binancebot.mobile.presentation.navigation.BinanceBotNavGraph
import com.binancebot.mobile.util.AppLogger
import com.binancebot.mobile.util.Constants
import kotlinx.coroutines.flow.filterIsInstance
import com.binancebot.mobile.presentation.navigation.Screen
import com.binancebot.mobile.presentation.theme.BinanceBotTheme
import com.binancebot.mobile.util.ConnectivityManager
import com.binancebot.mobile.util.PreferencesManager
import com.binancebot.mobile.util.SyncManager
import com.binancebot.mobile.util.TokenManager
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Holds pending deep link from notification tap so NavController can navigate after app is ready. */
object PendingDeepLink {
    val route = mutableStateOf<String?>(null)
}

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

    @Inject
    lateinit var webSocketManager: WebSocketManager

    @Inject
    lateinit var positionUpdateStore: PositionUpdateStore

    @Inject
    lateinit var notificationTrigger: com.binancebot.mobile.util.NotificationTrigger

    /**
     * Permission launcher for POST_NOTIFICATIONS (Android 13+).
     * Must be registered before onCreate lifecycle.
     */
    private val notificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            AppLogger.d("MainActivity", "Notification permission granted")
        } else {
            AppLogger.w("MainActivity", "Notification permission denied - push notifications will not work")
        }
    }
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Request notification permission for Android 13+ (API 33)
        requestNotificationPermission()
        
        if (tokenManager.isLoggedIn()) {
            val wsUrl = Constants.BASE_URL
                .replace("http://", "ws://")
                .replace("https://", "wss://") + "ws/positions"
            webSocketManager.connect(wsUrl)
            lifecycleScope.launch {
                webSocketManager.updates
                    .filterIsInstance<UpdateMessage.PositionUpdate>()
                    .collect { positionUpdateStore.apply(it) }
            }
            notificationTrigger.startListening()
        }
        
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
        if (deepLink != null) {
            PendingDeepLink.route.value = deepLink
        }
        if (tradeId != null) {
            PendingDeepLink.route.value = Screen.Trades.route
        }
        if (strategyId != null) {
            PendingDeepLink.route.value = "strategy_details/$strategyId"
        }
    }

    /**
     * Request POST_NOTIFICATIONS permission on Android 13+ (API 33).
     * Without this permission, push notifications will not be shown.
     */
    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            when {
                ContextCompat.checkSelfPermission(
                    this,
                    Manifest.permission.POST_NOTIFICATIONS
                ) == PackageManager.PERMISSION_GRANTED -> {
                    AppLogger.d("MainActivity", "Notification permission already granted")
                }
                shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS) -> {
                    // User previously denied - still request (they can still grant)
                    AppLogger.d("MainActivity", "Requesting notification permission (rationale needed)")
                    notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                }
                else -> {
                    // First time or "don't ask again" - request anyway
                    AppLogger.d("MainActivity", "Requesting notification permission")
                    notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                }
            }
        } else {
            // Android 12 and below - permission granted by default via manifest
            AppLogger.d("MainActivity", "Notification permission not required (Android < 13)")
        }
    }
}

@Composable
fun BinanceBotApp(tokenManager: TokenManager) {
    val navController = rememberNavController()
    var startDestination by remember { mutableStateOf<String?>(null) }
    var isValidating by remember { mutableStateOf(true) }
    
    // Validate token on app start (no network = safe fallback to login, no crash)
    LaunchedEffect(Unit) {
        try {
            if (tokenManager.isLoggedIn()) {
                val refreshedToken = tokenManager.refreshToken()
                if (refreshedToken != null) {
                    startDestination = Screen.Home.route
                } else {
                    tokenManager.clearTokens()
                    startDestination = Screen.Login.route
                }
            } else {
                startDestination = Screen.Login.route
            }
        } catch (_: Exception) {
            startDestination = Screen.Login.route
        } finally {
            isValidating = false
        }
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
        val pendingRoute by PendingDeepLink.route
        LaunchedEffect(pendingRoute) {
            pendingRoute?.let { route ->
                navController.navigate(route) {
                    popUpTo(navController.graph.startDestinationId) { saveState = true }
                    launchSingleTop = true
                    restoreState = true
                }
                PendingDeepLink.route.value = null
            }
        }
        BinanceBotNavGraph(
            navController = navController,
            startDestination = startDestination!!
        )
    }
}
