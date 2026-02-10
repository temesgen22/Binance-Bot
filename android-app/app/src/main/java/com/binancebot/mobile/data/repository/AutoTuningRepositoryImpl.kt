package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.*
import com.binancebot.mobile.domain.repository.AutoTuningRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AutoTuningRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : AutoTuningRepository {
    
    override suspend fun enableAutoTuning(strategyId: String, config: AutoTuningConfigDto): Result<Unit> {
        return retryApiCall {
            val request = EnableAutoTuningRequestDto(config = config)
            val response = api.enableAutoTuning(strategyId, request)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(Unit)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun disableAutoTuning(strategyId: String): Result<Unit> {
        return retryApiCall {
            val response = api.disableAutoTuning(strategyId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(Unit)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun tuneNow(strategyId: String): Result<Unit> {
        return retryApiCall {
            val response = api.tuneNow(strategyId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(Unit)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getTuningStatus(strategyId: String): Result<TuningStatusResponseDto> {
        return retryApiCall {
            val response = api.getTuningStatus(strategyId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getTuningHistory(strategyId: String, limit: Int, offset: Int): Result<List<TuningHistoryItemDto>> {
        return retryApiCall {
            val response = api.getTuningHistory(strategyId, limit, offset)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> {
                    // Parse the response which is a map with "history" key
                    val history = (it.data as? Map<*, *>)?.get("history") as? List<*>
                    val historyItems = history?.mapNotNull { item ->
                        try {
                            val map = item as? Map<*, *>
                            if (map != null) {
                                TuningHistoryItemDto(
                                    id = map["id"] as? String ?: "",
                                    strategyId = map["strategy_id"] as? String ?: "",
                                    tuningTime = map["tuning_time"] as? String ?: "",
                                    oldParams = (map["old_params"] as? Map<*, *>)?.let { 
                                        it.mapKeys { (k, _) -> k.toString() }.mapValues { (_, v) -> v as Any }
                                    } as? Map<String, Any>,
                                    newParams = (map["new_params"] as? Map<*, *>)?.let { 
                                        it.mapKeys { (k, _) -> k.toString() }.mapValues { (_, v) -> v as Any }
                                    } as? Map<String, Any>,
                                    performanceBefore = (map["performance_before"] as? Map<*, *>)?.let { 
                                        it.mapKeys { (k, _) -> k.toString() }.mapValues { (_, v) -> v as Any }
                                    } as? Map<String, Any>,
                                    performanceAfter = (map["performance_after"] as? Map<*, *>)?.let { 
                                        it.mapKeys { (k, _) -> k.toString() }.mapValues { (_, v) -> v as Any }
                                    } as? Map<String, Any>,
                                    improvementPct = (map["improvement_pct"] as? Number)?.toDouble(),
                                    status = map["status"] as? String ?: "unknown"
                                )
                            } else null
                        } catch (e: Exception) {
                            null
                        }
                    } ?: emptyList()
                    Result.success(historyItems)
                }
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
}

