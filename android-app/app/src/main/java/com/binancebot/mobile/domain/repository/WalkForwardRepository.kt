package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.*

/**
 * Repository interface for Walk-Forward Analysis operations.
 */
interface WalkForwardRepository {
    suspend fun startWalkForwardAnalysis(request: WalkForwardRequestDto): Result<WalkForwardStartResponseDto>
    suspend fun getWalkForwardProgress(taskId: String): Result<WalkForwardProgressDto>
    suspend fun getWalkForwardResult(taskId: String): Result<WalkForwardResultDto>
    suspend fun getWalkForwardHistory(limit: Int = 50, offset: Int = 0, symbol: String? = null, strategyType: String? = null): Result<List<WalkForwardHistoryItemDto>>
}



