package com.binancebot.mobile.data.local.dao

import androidx.room.*
import com.binancebot.mobile.data.local.entities.StrategyEntity
import kotlinx.coroutines.flow.Flow

/**
 * DAO for Strategy entities.
 * ✅ CRITICAL: Returns Flow for reactive Room queries (source of truth).
 */
@Dao
interface StrategyDao {
    @Query("SELECT * FROM strategies ORDER BY name ASC")
    fun getAllStrategies(): Flow<List<StrategyEntity>>
    
    @Query("SELECT * FROM strategies WHERE id = :id")
    suspend fun getStrategyById(id: String): StrategyEntity?
    
    @Query("SELECT * FROM strategies WHERE status = :status ORDER BY name ASC")
    fun getStrategiesByStatus(status: String): Flow<List<StrategyEntity>>
    
    @Query("SELECT * FROM strategies WHERE symbol = :symbol ORDER BY name ASC")
    fun getStrategiesBySymbol(symbol: String): Flow<List<StrategyEntity>>
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertStrategy(strategy: StrategyEntity)
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertStrategies(strategies: List<StrategyEntity>)
    
    @Update
    suspend fun updateStrategy(strategy: StrategyEntity)
    
    @Query("DELETE FROM strategies WHERE id = :id")
    suspend fun deleteStrategy(id: String)
    
    @Query("DELETE FROM strategies")
    suspend fun clearAll()
}
