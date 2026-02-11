package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.local.dao.NotificationDao
import com.binancebot.mobile.data.local.entities.NotificationEntity
import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.NotificationDto
import com.binancebot.mobile.data.remote.dto.NotificationHistoryResponseDto
import com.binancebot.mobile.data.remote.dto.NotificationPreferencesDto
import com.binancebot.mobile.data.remote.dto.RegisterFcmTokenRequest
import com.binancebot.mobile.domain.model.Notification
import com.binancebot.mobile.domain.repository.NotificationRepository
import com.binancebot.mobile.util.ApiResult
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import com.google.gson.Gson
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class NotificationRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi,
    private val notificationDao: NotificationDao
) : NotificationRepository {
    
    override suspend fun registerFcmToken(
        fcmToken: String, 
        deviceId: String,
        deviceName: String?,
        appVersion: String?
    ): Result<Unit> {
        return retryApiCall {
            val response = api.registerFcmToken(
                RegisterFcmTokenRequest(
                    token = fcmToken,
                    deviceId = deviceId,
                    deviceType = "android",
                    clientType = "android_app",
                    deviceName = deviceName,
                    appVersion = appVersion
                )
            )
            response.toResult()
        }.let {
            when (it) {
                is ApiResult.Success -> Result.success(Unit)
                is ApiResult.Error -> Result.failure(Exception(it.message))
                is ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun updateNotificationPreferences(preferences: NotificationPreferencesDto): Result<NotificationPreferencesDto> {
        return retryApiCall {
            val response = api.updateNotificationPreferences(preferences)
            response.toResult()
        }.let {
            when (it) {
                is ApiResult.Success -> Result.success(it.data)
                is ApiResult.Error -> Result.failure(Exception(it.message))
                is ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getNotificationHistory(
        limit: Int,
        offset: Int,
        category: String?,
        type: String?
    ): Result<Pair<List<Notification>, Int>> {
        return retryApiCall {
            val response = api.getNotificationHistory(
                limit = limit,
                offset = offset,
                category = category,
                type = type
            )
            response.toResult()
        }.let {
            when (it) {
                is ApiResult.Success -> {
                    val historyResponse = it.data as? NotificationHistoryResponseDto
                    if (historyResponse != null) {
                        // Save to local database
                        val notifications = historyResponse.notifications.map { dto ->
                            NotificationEntity.fromDomain(dto.toDomain())
                        }
                        notificationDao.insertNotifications(notifications)
                        
                        val domainNotifications = historyResponse.notifications.map { it.toDomain() }
                        Result.success(Pair(domainNotifications, historyResponse.unreadCount))
                    } else {
                        Result.failure(Exception("Invalid response format"))
                    }
                }
                is ApiResult.Error -> Result.failure(Exception(it.message))
                is ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun markNotificationAsRead(notificationId: String): Result<Unit> {
        return retryApiCall {
            val response = api.markNotificationAsRead(notificationId)
            response.toResult()
        }.let {
            when (it) {
                is ApiResult.Success -> {
                    // Update local database
                    notificationDao.markAsRead(notificationId)
                    Result.success(Unit)
                }
                is ApiResult.Error -> Result.failure(Exception(it.message))
                is ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun deleteNotification(notificationId: String): Result<Unit> {
        return retryApiCall {
            val response = api.deleteNotification(notificationId)
            response.toResult()
        }.let {
            when (it) {
                is ApiResult.Success -> {
                    // Delete from local database
                    notificationDao.deleteNotification(notificationId)
                    Result.success(Unit)
                }
                is ApiResult.Error -> Result.failure(Exception(it.message))
                is ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
}

// Extension functions to convert DTOs to domain models
private fun NotificationDto.toDomain(): Notification {
    return Notification(
        id = id,
        type = type,
        category = category,
        title = title,
        message = message,
        timestamp = timestamp,
        read = read,
        data = data?.let { Gson().toJson(it) },
        actionUrl = actionUrl,
        priority = priority
    )
}

