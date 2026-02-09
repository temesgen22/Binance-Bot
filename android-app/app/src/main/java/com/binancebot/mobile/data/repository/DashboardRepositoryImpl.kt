package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.DashboardOverviewDto
import com.binancebot.mobile.domain.repository.DashboardRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class DashboardRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : DashboardRepository {
    
    override suspend fun getDashboardOverview(
        startDate: String?,
        endDate: String?,
        accountId: String?
    ): Result<DashboardOverviewDto> {
        return retryApiCall {
            val response = api.getDashboardOverview(
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
