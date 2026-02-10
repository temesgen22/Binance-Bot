package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceListDto
import com.binancebot.mobile.domain.repository.StrategyPerformanceRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class StrategyPerformanceRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : StrategyPerformanceRepository {
    
    override suspend fun getStrategyPerformance(
        strategyName: String?,
        symbol: String?,
        status: String?,
        rankBy: String?,
        startDate: String?,
        endDate: String?,
        accountId: String?
    ): Result<StrategyPerformanceListDto> {
        return retryApiCall {
            val response = api.getStrategyPerformance(
                strategyName = strategyName,
                symbol = symbol,
                status = status,
                rankBy = rankBy ?: "total_pnl",
                startDate = startDate,
                endDate = endDate,
                accountId = accountId
            )
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getStrategyPerformanceById(strategyId: String): Result<StrategyPerformanceDto> {
        return retryApiCall {
            val response = api.getStrategyPerformanceById(strategyId)
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





























