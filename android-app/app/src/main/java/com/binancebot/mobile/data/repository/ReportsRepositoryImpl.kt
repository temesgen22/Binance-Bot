package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.TradingReportDto
import com.binancebot.mobile.domain.repository.ReportsRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ReportsRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : ReportsRepository {
    
    override suspend fun getTradingReport(
        strategyId: String?,
        strategyName: String?,
        symbol: String?,
        startDate: String?,
        endDate: String?,
        accountId: String?
    ): Result<TradingReportDto> {
        return retryApiCall {
            val response = api.getTradingReport(
                strategyId = strategyId,
                strategyName = strategyName,
                symbol = symbol,
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
}





















