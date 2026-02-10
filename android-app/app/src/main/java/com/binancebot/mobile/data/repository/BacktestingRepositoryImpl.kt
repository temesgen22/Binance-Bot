package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.BacktestRequestDto
import com.binancebot.mobile.data.remote.dto.BacktestResultDto
import com.binancebot.mobile.domain.repository.BacktestingRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class BacktestingRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : BacktestingRepository {
    
    override suspend fun runBacktest(request: BacktestRequestDto): Result<BacktestResultDto> {
        return retryApiCall {
            val response = api.runBacktest(request)
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



