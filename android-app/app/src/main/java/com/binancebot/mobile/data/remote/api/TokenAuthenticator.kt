package com.binancebot.mobile.data.remote.api

import com.binancebot.mobile.data.remote.dto.RefreshTokenRequest
import com.binancebot.mobile.util.TokenManager
import okhttp3.Authenticator
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route
import javax.inject.Provider

/**
 * Token Authenticator for automatic token refresh on 401 errors.
 * 
 * ✅ CRITICAL FIX: Uses Authenticator instead of Interceptor to avoid runBlocking.
 * This is the correct way to handle token refresh in OkHttp.
 * 
 * Uses Provider<BinanceBotApi> to break circular dependency with NetworkModule.
 */
class TokenAuthenticator(
    private val tokenManager: TokenManager,
    private val apiProvider: Provider<BinanceBotApi>
) : Authenticator {
    
    private val refreshLock = Any()
    @Volatile
    private var isRefreshing = false
    
    override fun authenticate(route: Route?, response: Response): Request? {
        // Prevent infinite retry loops
        if (responseCount(response) >= 2) {
            tokenManager.clearTokens()
            return null
        }
        
        synchronized(refreshLock) {
            // If another request is already refreshing, wait and use new token
            if (isRefreshing) {
                Thread.sleep(100)
                val newToken = tokenManager.getAccessToken()
                return if (newToken != null) {
                    response.request.newBuilder()
                        .header("Authorization", "Bearer $newToken")
                        .build()
                } else null
            }
            
            isRefreshing = true
            try {
                val refreshToken = tokenManager.getRefreshToken() ?: return null
                
                // Use synchronous call (Authenticator must be synchronous)
                // Get API instance from provider to break circular dependency
                val call = apiProvider.get().refreshTokenSync(RefreshTokenRequest(refreshToken))
                val refreshResponse = call.execute()
                
                if (refreshResponse.isSuccessful && refreshResponse.body() != null) {
                    val tokenResponse = refreshResponse.body()!!
                    tokenManager.saveTokens(
                        tokenResponse.accessToken,
                        tokenResponse.refreshToken
                    )
                    
                    return response.request.newBuilder()
                        .header("Authorization", "Bearer ${tokenResponse.accessToken}")
                        .build()
                } else {
                    tokenManager.clearTokens()
                    return null
                }
            } catch (e: Exception) {
                tokenManager.clearTokens()
                return null
            } finally {
                isRefreshing = false
            }
        }
    }
    
    private fun responseCount(response: Response): Int {
        var result = 1
        var current = response.priorResponse
        while (current != null) {
            result++
            current = current.priorResponse
        }
        return result
    }
}

