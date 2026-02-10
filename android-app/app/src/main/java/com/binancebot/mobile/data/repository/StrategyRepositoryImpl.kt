package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.domain.model.Strategy
import com.binancebot.mobile.domain.repository.StrategyRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class StrategyRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : StrategyRepository {
    
    override suspend fun getStrategies(): Result<List<Strategy>> {
        return retryApiCall {
            val response = api.getStrategies()
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> {
                    Result.success(it.data.map { dto -> dto.toDomain() })
                }
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getStrategy(strategyId: String): Result<Strategy> {
        return retryApiCall {
            val response = api.getStrategy(strategyId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data.toDomain())
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun createStrategy(request: com.binancebot.mobile.data.remote.dto.CreateStrategyRequest): Result<Strategy> {
        return retryApiCall {
            val response = api.createStrategy(request)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data.toDomain())
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun updateStrategy(strategyId: String, request: com.binancebot.mobile.data.remote.dto.UpdateStrategyRequest): Result<Strategy> {
        return retryApiCall {
            val response = api.updateStrategy(strategyId, request)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data.toDomain())
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun deleteStrategy(strategyId: String): Result<Unit> {
        return retryApiCall {
            val response = api.deleteStrategy(strategyId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(Unit)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun startStrategy(strategyId: String): Result<Unit> {
        return retryApiCall {
            val response = api.startStrategy(strategyId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(Unit)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun stopStrategy(strategyId: String): Result<Unit> {
        return retryApiCall {
            val response = api.stopStrategy(strategyId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(Unit)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getStrategyStats(strategyId: String): Result<com.binancebot.mobile.data.remote.dto.StrategyStatsDto> {
        return retryApiCall {
            val response = api.getStrategyStats(strategyId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getStrategyActivity(strategyId: String, limit: Int): Result<List<com.binancebot.mobile.data.remote.dto.StrategyActivityDto>> {
        return retryApiCall {
            val response = api.getStrategyActivity(strategyId, limit)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
}
