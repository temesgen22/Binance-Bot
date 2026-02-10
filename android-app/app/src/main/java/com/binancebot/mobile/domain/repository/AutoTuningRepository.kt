package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.*

/**
 * Repository interface for Auto-Tuning operations.
 */
interface AutoTuningRepository {
    suspend fun enableAutoTuning(strategyId: String, config: AutoTuningConfigDto): Result<Unit>
    suspend fun disableAutoTuning(strategyId: String): Result<Unit>
    suspend fun tuneNow(strategyId: String): Result<Unit>
    suspend fun getTuningStatus(strategyId: String): Result<TuningStatusResponseDto>
    suspend fun getTuningHistory(strategyId: String, limit: Int = 50, offset: Int = 0): Result<List<TuningHistoryItemDto>>
}



