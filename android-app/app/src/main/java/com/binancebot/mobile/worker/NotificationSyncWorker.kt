package com.binancebot.mobile.worker

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.binancebot.mobile.domain.repository.NotificationRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject

/**
 * WorkManager worker for syncing notifications with backend
 * Runs periodically to check for missed notifications
 */
@HiltWorker
class NotificationSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val notificationRepository: NotificationRepository
) : CoroutineWorker(context, params) {
    
    override suspend fun doWork(): androidx.work.ListenableWorker.Result {
        return try {
            // Sync notification history from backend
            val result = notificationRepository.getNotificationHistory(
                limit = 50,
                offset = 0,
                category = null,
                type = null
            )
            if (result.isSuccess) {
                androidx.work.ListenableWorker.Result.success()
            } else {
                androidx.work.ListenableWorker.Result.retry()
            }
        } catch (e: Exception) {
            androidx.work.ListenableWorker.Result.failure()
        }
    }
}

