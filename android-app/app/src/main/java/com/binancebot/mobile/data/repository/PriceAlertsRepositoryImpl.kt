package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.CreatePriceAlertRequest
import com.binancebot.mobile.data.remote.dto.PriceAlertDto
import com.binancebot.mobile.data.remote.dto.UpdatePriceAlertRequest
import com.binancebot.mobile.domain.repository.PriceAlertsRepository
import com.binancebot.mobile.util.ApiResult
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class PriceAlertsRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : PriceAlertsRepository {

    override suspend fun getPriceAlerts(enabled: Boolean?): Result<List<PriceAlertDto>> {
        return retryApiCall {
            api.getPriceAlerts(enabled).toResult()
        }.let {
            when (it) {
                is ApiResult.Success -> Result.success(it.data.alerts)
                is ApiResult.Error -> Result.failure(Exception(it.message))
                is ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }

    override suspend fun getPriceAlert(id: String): Result<PriceAlertDto> {
        return retryApiCall {
            api.getPriceAlert(id).toResult()
        }.let {
            when (it) {
                is ApiResult.Success -> Result.success(it.data)
                is ApiResult.Error -> Result.failure(Exception(it.message))
                is ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }

    override suspend fun createPriceAlert(request: CreatePriceAlertRequest): Result<PriceAlertDto> {
        return retryApiCall {
            api.createPriceAlert(request).toResult()
        }.let {
            when (it) {
                is ApiResult.Success -> Result.success(it.data)
                is ApiResult.Error -> Result.failure(Exception(it.message))
                is ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }

    override suspend fun updatePriceAlert(id: String, request: UpdatePriceAlertRequest): Result<PriceAlertDto> {
        return retryApiCall {
            api.updatePriceAlert(id, request).toResult()
        }.let {
            when (it) {
                is ApiResult.Success -> Result.success(it.data)
                is ApiResult.Error -> Result.failure(Exception(it.message))
                is ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }

    override suspend fun deletePriceAlert(id: String): Result<Unit> {
        return retryApiCall {
            api.deletePriceAlert(id).toResult()
        }.let {
            when (it) {
                is ApiResult.Success -> Result.success(Unit)
                is ApiResult.Error -> Result.failure(Exception(it.message))
                is ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
}
