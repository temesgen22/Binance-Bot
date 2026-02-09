package com.binancebot.mobile.data.local.database

import androidx.room.Database
import androidx.room.RoomDatabase
import com.binancebot.mobile.data.local.dao.StrategyDao
import com.binancebot.mobile.data.local.dao.TradeDao
import com.binancebot.mobile.data.local.entities.StrategyEntity
import com.binancebot.mobile.data.local.entities.TradeEntity

/**
 * Room database for local caching.
 * ✅ CRITICAL: This is the source of truth for UI.
 */
@Database(
    entities = [
        StrategyEntity::class,
        TradeEntity::class
    ],
    version = 1,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun strategyDao(): StrategyDao
    abstract fun tradeDao(): TradeDao
    
    companion object {
        const val DATABASE_NAME = "binance_bot_db"
    }
}


































