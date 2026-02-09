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
