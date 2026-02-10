package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.*
import com.binancebot.mobile.domain.repository.WalkForwardRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class WalkForwardRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : WalkForwardRepository {
    
    override suspend fun startWalkForwardAnalysis(request: WalkForwardRequestDto): Result<WalkForwardStartResponseDto> {
        return retryApiCall {
            val response = api.startWalkForwardAnalysis(request)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getWalkForwardProgress(taskId: String): Result<WalkForwardProgressDto> {
        return retryApiCall {
            val response = api.getWalkForwardProgress(taskId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getWalkForwardResult(taskId: String): Result<WalkForwardResultDto> {
        return retryApiCall {
            val response = api.getWalkForwardResult(taskId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getWalkForwardHistory(limit: Int, offset: Int, symbol: String?, strategyType: String?): Result<List<WalkForwardHistoryItemDto>> {
        return retryApiCall {
            val response = api.getWalkForwardHistory(limit, offset, symbol, strategyType)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> {
                    // Parse the response which is a map with "analyses" key
                    val analyses = (it.data as? Map<*, *>)?.get("analyses") as? List<*>
                    val historyItems = analyses?.mapNotNull { item ->
                        try {
                            // Convert map to DTO - this is a simplified approach
                            // In production, you'd want proper JSON deserialization
                            val map = item as? Map<*, *>
                            if (map != null) {
                                WalkForwardHistoryItemDto(
                                    id = map["id"] as? String ?: "",
                                    taskId = map["task_id"] as? String,
                                    symbol = map["symbol"] as? String ?: "",
                                    strategyType = map["strategy_type"] as? String ?: "",
                                    name = map["name"] as? String,
                                    startTime = map["start_time"] as? String ?: "",
                                    endTime = map["end_time"] as? String ?: "",
                                    status = map["status"] as? String ?: "unknown",
                                    totalWindows = (map["total_windows"] as? Number)?.toInt() ?: 0,
                                    completedWindows = (map["completed_windows"] as? Number)?.toInt(),
                                    totalReturnPct = (map["total_return_pct"] as? Number)?.toDouble(),
                                    createdAt = map["created_at"] as? String,
                                    completedAt = map["completed_at"] as? String
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



