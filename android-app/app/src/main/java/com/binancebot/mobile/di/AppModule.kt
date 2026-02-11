package com.binancebot.mobile.di

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.preferencesDataStore
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "settings")

@Module
@InstallIn(SingletonComponent::class)
object AppModule {
    
    @Provides
    @Singleton
    fun provideDataStore(@ApplicationContext context: Context): DataStore<Preferences> {
        return context.dataStore
    }
    
    @Provides
    @Singleton
    fun providePreferencesManager(@ApplicationContext context: Context): com.binancebot.mobile.util.PreferencesManager {
        return com.binancebot.mobile.util.PreferencesManager(context)
    }
    
    @Provides
    @Singleton
    fun provideConnectivityManager(@ApplicationContext context: Context): com.binancebot.mobile.util.ConnectivityManager {
        return com.binancebot.mobile.util.ConnectivityManager(context)
    }
    
    @Provides
    @Singleton
    fun provideSyncManager(
        @ApplicationContext context: Context,
        connectivityManager: com.binancebot.mobile.util.ConnectivityManager
    ): com.binancebot.mobile.util.SyncManager {
        return com.binancebot.mobile.util.SyncManager(context, connectivityManager)
    }
    
    @Provides
    @Singleton
    fun provideNotificationManager(
        @ApplicationContext context: Context,
        notificationDao: com.binancebot.mobile.data.local.dao.NotificationDao
    ): com.binancebot.mobile.util.NotificationManager {
        return com.binancebot.mobile.util.NotificationManager(context, notificationDao)
    }
}































