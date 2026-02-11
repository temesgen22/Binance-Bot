package com.binancebot.mobile.data.local.database

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.binancebot.mobile.data.local.dao.NotificationDao
import com.binancebot.mobile.data.local.dao.StrategyDao
import com.binancebot.mobile.data.local.dao.TradeDao
import com.binancebot.mobile.data.local.entities.NotificationEntity
import com.binancebot.mobile.data.local.entities.StrategyEntity
import com.binancebot.mobile.data.local.entities.TradeEntity

/**
 * Room database for local caching.
 * ✅ CRITICAL: This is the source of truth for UI.
 */
@Database(
    entities = [
        StrategyEntity::class,
        TradeEntity::class,
        NotificationEntity::class
    ],
    version = 2,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun strategyDao(): StrategyDao
    abstract fun tradeDao(): TradeDao
    abstract fun notificationDao(): NotificationDao
    
    companion object {
        const val DATABASE_NAME = "binance_bot_db"
        
        /**
         * Migration from version 1 to 2: Add notifications table
         */
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL("""
                    CREATE TABLE IF NOT EXISTS notifications (
                        id TEXT NOT NULL PRIMARY KEY,
                        type TEXT NOT NULL,
                        category TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        read INTEGER NOT NULL DEFAULT 0,
                        data TEXT,
                        actionUrl TEXT,
                        priority INTEGER NOT NULL DEFAULT 0
                    )
                """.trimIndent())
                database.execSQL("CREATE INDEX IF NOT EXISTS index_notifications_type ON notifications(type)")
                database.execSQL("CREATE INDEX IF NOT EXISTS index_notifications_category ON notifications(category)")
                database.execSQL("CREATE INDEX IF NOT EXISTS index_notifications_timestamp ON notifications(timestamp)")
                database.execSQL("CREATE INDEX IF NOT EXISTS index_notifications_read ON notifications(read)")
            }
        }
    }
}







































