package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.MarketAnalysisResponse
import com.binancebot.mobile.domain.repository.MarketAnalyzerRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class MarketAnalyzerRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : MarketAnalyzerRepository {
    
    override suspend fun analyzeMarket(
        symbol: String,
        interval: String,
        lookbackPeriod: Int,
        emaFastPeriod: Int,
        emaSlowPeriod: Int,
        maxEmaSpreadPct: Double,
        rsiPeriod: Int,
        swingPeriod: Int
    ): Result<MarketAnalysisResponse> {
        return retryApiCall {
            val response = api.analyzeMarket(
                symbol = symbol,
                interval = interval,
                lookbackPeriod = lookbackPeriod,
                emaFastPeriod = emaFastPeriod,
                emaSlowPeriod = emaSlowPeriod,
                maxEmaSpreadPct = maxEmaSpreadPct,
                rsiPeriod = rsiPeriod,
                swingPeriod = swingPeriod
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





















