package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto
import com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto
import com.binancebot.mobile.domain.repository.RiskManagementRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class RiskManagementRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : RiskManagementRepository {
    
    override suspend fun getPortfolioRiskStatus(accountId: String?): Result<PortfolioRiskStatusDto> {
        return retryApiCall {
            val response = api.getPortfolioRiskStatus(accountId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getRiskConfig(accountId: String?): Result<RiskManagementConfigDto> {
        return retryApiCall {
            val response = api.getRiskConfig(accountId)
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
