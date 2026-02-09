package com.binancebot.mobile.util

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.RefreshTokenRequest
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Provider
import javax.inject.Singleton

/**
 * Token Manager for secure token storage and refresh.
 */
@Singleton
class TokenManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val authApi: Provider<BinanceBotApi>
) {
    private val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()
    
    private val encryptedPrefs = EncryptedSharedPreferences.create(
        context,
        "token_prefs",
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )
    
    @Volatile
    private var isRefreshing = false
    
    fun saveTokens(accessToken: String, refreshToken: String) {
        encryptedPrefs.edit()
            .putString("access_token", accessToken)
            .putString("refresh_token", refreshToken)
            .apply()
    }
    
    fun getAccessToken(): String? {
        return encryptedPrefs.getString("access_token", null)
    }
    
    fun getRefreshToken(): String? {
        return encryptedPrefs.getString("refresh_token", null)
    }
    
    suspend fun refreshToken(): String? {
        // Prevent multiple simultaneous refresh calls
        if (isRefreshing) {
            // Wait for ongoing refresh
            while (isRefreshing) {
                kotlinx.coroutines.delay(100)
            }
            return getAccessToken()
        }
        
        val refreshToken = getRefreshToken() ?: return null
        
        isRefreshing = true
        return try {
            // Call refresh API
            val response = authApi.get().refreshToken(RefreshTokenRequest(refreshToken))
            
            if (response.isSuccessful && response.body() != null) {
                val tokenResponse = response.body()!!
                saveTokens(tokenResponse.accessToken, tokenResponse.refreshToken)
                tokenResponse.accessToken
            } else {
                // Refresh failed - clear tokens
                clearTokens()
                null
            }
        } catch (e: Exception) {
            android.util.Log.e("TokenManager", "Token refresh failed", e)
            clearTokens()
            null
        } finally {
            isRefreshing = false
        }
    }
    
    fun clearTokens() {
        encryptedPrefs.edit().clear().apply()
    }
    
    fun isLoggedIn(): Boolean {
        return getAccessToken() != null
    }
}



