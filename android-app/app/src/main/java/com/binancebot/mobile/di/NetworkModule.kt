package com.binancebot.mobile.di

import com.binancebot.mobile.BuildConfig
import com.binancebot.mobile.data.remote.api.AuthInterceptor
import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.api.TokenAuthenticator
import com.binancebot.mobile.util.Constants
import com.binancebot.mobile.util.TokenManager
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.Cache
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import java.io.File
import java.util.concurrent.TimeUnit
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Provider
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    
    @Provides
    @Singleton
    fun provideOkHttpClient(
        tokenManager: TokenManager,
        apiProvider: Provider<BinanceBotApi>,
        authInterceptor: AuthInterceptor,
        @ApplicationContext context: android.content.Context
    ): OkHttpClient {
        // ✅ OPTIMIZATION: Only log in debug builds to save battery
        val loggingInterceptor = HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) {
                HttpLoggingInterceptor.Level.BODY
            } else {
                HttpLoggingInterceptor.Level.NONE
            }
        }
        
        // ✅ OPTIMIZATION: Add HTTP cache for offline support and reduced network calls
        val cacheSize = 10 * 1024 * 1024L // 10 MB
        val cacheDir = File(context.cacheDir, "http_cache")
        val cache = Cache(cacheDir, cacheSize)
        
        // Create TokenAuthenticator with provider to break circular dependency
        val tokenAuthenticator = TokenAuthenticator(tokenManager, apiProvider)
        
        return OkHttpClient.Builder()
            .addInterceptor(authInterceptor)  // ✅ Add Authorization header to all requests
            .authenticator(tokenAuthenticator)  // ✅ Use authenticator for token refresh on 401
            .addInterceptor(loggingInterceptor)
            .cache(cache)  // ✅ OPTIMIZATION: Enable HTTP caching
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()
    }
    
    @Provides
    @Singleton
    fun provideGson(): Gson {
        return GsonBuilder()
            .setLenient()  // Allow lenient parsing for more flexible JSON handling
            .serializeNulls()  // Include null values in serialization
            .create()
    }
    
    @Provides
    @Singleton
    fun provideRetrofit(okHttpClient: OkHttpClient, gson: Gson): Retrofit {
        return Retrofit.Builder()
            .baseUrl(Constants.BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
    }
    
    @Provides
    @Singleton
    fun provideBinanceBotApi(retrofit: Retrofit): BinanceBotApi {
        return retrofit.create(BinanceBotApi::class.java)
    }
}
