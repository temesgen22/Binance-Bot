package com.binancebot.mobile.data.local.dao

import androidx.room.*
import com.binancebot.mobile.data.local.entities.TradeEntity
import kotlinx.coroutines.flow.Flow

/**
 * DAO for Trade entities.
 * ✅ CRITICAL: Returns Flow for reactive Room queries (source of truth).
 */
@Dao
interface TradeDao {
    @Query("SELECT * FROM trades ORDER BY timestamp DESC")
    fun getAllTrades(): Flow<List<TradeEntity>>
    
    @Query("SELECT * FROM trades WHERE strategyId = :strategyId ORDER BY timestamp DESC")
    fun getTradesByStrategy(strategyId: String): Flow<List<TradeEntity>>
    
    @Query("SELECT * FROM trades WHERE id = :id")
    suspend fun getTradeById(id: String): TradeEntity?
    
    @Query("SELECT * FROM trades WHERE orderId = :orderId")
    suspend fun getTradeByOrderId(orderId: Long): TradeEntity?
    
    @Query("SELECT * FROM trades WHERE symbol = :symbol ORDER BY timestamp DESC")
    fun getTradesBySymbol(symbol: String): Flow<List<TradeEntity>>
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTrade(trade: TradeEntity)
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTrades(trades: List<TradeEntity>)
    
    @Query("DELETE FROM trades WHERE strategyId = :strategyId")
    suspend fun deleteTradesByStrategy(strategyId: String)
    
    @Query("DELETE FROM trades")
    suspend fun clearAll()
}
































