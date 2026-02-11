package com.binancebot.mobile.data.local.dao

import androidx.room.*
import com.binancebot.mobile.data.local.entities.NotificationEntity
import kotlinx.coroutines.flow.Flow

/**
 * DAO for Notification entities.
 */
@Dao
interface NotificationDao {
    @Query("SELECT * FROM notifications ORDER BY timestamp DESC")
    fun getAllNotifications(): Flow<List<NotificationEntity>>
    
    @Query("SELECT * FROM notifications WHERE id = :id")
    suspend fun getNotificationById(id: String): NotificationEntity?
    
    @Query("SELECT * FROM notifications WHERE type = :type ORDER BY timestamp DESC")
    fun getNotificationsByType(type: String): Flow<List<NotificationEntity>>
    
    @Query("SELECT * FROM notifications WHERE category = :category ORDER BY timestamp DESC")
    fun getNotificationsByCategory(category: String): Flow<List<NotificationEntity>>
    
    @Query("SELECT * FROM notifications WHERE read = 0 ORDER BY timestamp DESC")
    fun getUnreadNotifications(): Flow<List<NotificationEntity>>
    
    @Query("SELECT COUNT(*) FROM notifications WHERE read = 0")
    fun getUnreadCount(): Flow<Int>
    
    @Query("SELECT * FROM notifications WHERE timestamp >= :fromTimestamp AND timestamp <= :toTimestamp ORDER BY timestamp DESC")
    fun getNotificationsByDateRange(fromTimestamp: Long, toTimestamp: Long): Flow<List<NotificationEntity>>
    
    @Query("SELECT * FROM notifications WHERE title LIKE :query OR message LIKE :query ORDER BY timestamp DESC")
    fun searchNotifications(query: String): Flow<List<NotificationEntity>>
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertNotification(notification: NotificationEntity)
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertNotifications(notifications: List<NotificationEntity>)
    
    @Update
    suspend fun updateNotification(notification: NotificationEntity)
    
    @Query("UPDATE notifications SET read = 1 WHERE id = :id")
    suspend fun markAsRead(id: String)
    
    @Query("UPDATE notifications SET read = 1 WHERE read = 0")
    suspend fun markAllAsRead()
    
    @Query("DELETE FROM notifications WHERE id = :id")
    suspend fun deleteNotification(id: String)
    
    @Query("DELETE FROM notifications WHERE timestamp < :beforeTimestamp")
    suspend fun deleteOldNotifications(beforeTimestamp: Long)
    
    @Query("DELETE FROM notifications")
    suspend fun clearAll()
}





