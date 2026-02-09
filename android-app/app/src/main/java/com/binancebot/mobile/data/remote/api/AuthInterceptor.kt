package com.binancebot.mobile.data.remote.api

import com.binancebot.mobile.util.TokenManager
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject

/**
 * Interceptor to add Authorization header to all API requests.
 * This ensures the access token is included in every request.
 */
class AuthInterceptor @Inject constructor(
    private val tokenManager: TokenManager
) : Interceptor {
    
    override fun intercept(chain: Interceptor.Chain): Response {
        val originalRequest = chain.request()
        
        // Get access token
        val accessToken = tokenManager.getAccessToken()
        
        // Add Authorization header if token exists
        val requestBuilder = originalRequest.newBuilder()
        if (accessToken != null) {
            requestBuilder.header("Authorization", "Bearer $accessToken")
        }
        
        val request = requestBuilder.build()
        return chain.proceed(request)
    }
}



























