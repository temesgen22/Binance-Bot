package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.TestAccountRequestDto
import com.binancebot.mobile.data.remote.dto.TestAccountResponseDto
import com.binancebot.mobile.domain.repository.TestAccountsRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class TestAccountsRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : TestAccountsRepository {
    
    override suspend fun testAccount(request: TestAccountRequestDto): Result<TestAccountResponseDto> {
        return retryApiCall {
            val response = api.testAccount(request)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun quickTestAccount(
        apiKey: String,
        apiSecret: String,
        testnet: Boolean
    ): Result<TestAccountResponseDto> {
        return retryApiCall {
            val response = api.quickTestAccount(apiKey, apiSecret, testnet)
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





















