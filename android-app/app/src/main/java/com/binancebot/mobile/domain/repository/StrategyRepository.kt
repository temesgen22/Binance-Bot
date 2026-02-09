package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.domain.model.Strategy

/**
 * Repository interface for Strategy operations.
 */
interface StrategyRepository {
    suspend fun getStrategies(): Result<List<Strategy>>
    suspend fun getStrategy(strategyId: String): Result<Strategy>
    suspend fun createStrategy(request: com.binancebot.mobile.data.remote.dto.CreateStrategyRequest): Result<Strategy>
    suspend fun updateStrategy(strategyId: String, request: com.binancebot.mobile.data.remote.dto.UpdateStrategyRequest): Result<Strategy>
    suspend fun deleteStrategy(strategyId: String): Result<Unit>
    suspend fun startStrategy(strategyId: String): Result<Unit>
    suspend fun stopStrategy(strategyId: String): Result<Unit>
    suspend fun getStrategyStats(strategyId: String): Result<com.binancebot.mobile.data.remote.dto.StrategyStatsDto>
}
