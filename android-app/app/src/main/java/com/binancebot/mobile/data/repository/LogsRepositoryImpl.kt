package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.LogResponse
import com.binancebot.mobile.domain.repository.LogsRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class LogsRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : LogsRepository {
    
    override suspend fun getLogs(
        symbol: String?,
        level: String?,
        dateFrom: String?,
        dateTo: String?,
        searchText: String?,
        limit: Int,
        offset: Int,
        reverse: Boolean
    ): Result<LogResponse> {
        return retryApiCall {
            val response = api.getLogs(
                symbol = symbol,
                level = level,
                dateFrom = dateFrom,
                dateTo = dateTo,
                searchText = searchText,
                limit = limit,
                offset = offset,
                reverse = reverse
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





















