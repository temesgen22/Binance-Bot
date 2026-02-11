package com.binancebot.mobile.di

import android.content.Context
import androidx.room.Room
import com.binancebot.mobile.data.local.dao.NotificationDao
import com.binancebot.mobile.data.local.dao.StrategyDao
import com.binancebot.mobile.data.local.dao.TradeDao
import com.binancebot.mobile.data.local.database.AppDatabase
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * Database module for Room.
 */
@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    
    @Provides
    @Singleton
    fun provideAppDatabase(@ApplicationContext context: Context): AppDatabase {
        return Room.databaseBuilder(
            context,
            AppDatabase::class.java,
            AppDatabase.DATABASE_NAME
        )
            .addMigrations(AppDatabase.MIGRATION_1_2)
            .fallbackToDestructiveMigration() // For development - remove in production
            .build()
    }
    
    @Provides
    fun provideStrategyDao(database: AppDatabase): StrategyDao {
        return database.strategyDao()
    }
    
    @Provides
    fun provideTradeDao(database: AppDatabase): TradeDao {
        return database.tradeDao()
    }
    
    @Provides
    fun provideNotificationDao(database: AppDatabase): NotificationDao {
        return database.notificationDao()
    }
}







































