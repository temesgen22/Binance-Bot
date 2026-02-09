package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.MarketAnalysisResponse

interface MarketAnalyzerRepository {
    suspend fun analyzeMarket(
        symbol: String,
        interval: String = "5m",
        lookbackPeriod: Int = 150,
        emaFastPeriod: Int = 20,
        emaSlowPeriod: Int = 50,
        maxEmaSpreadPct: Double = 0.005,
        rsiPeriod: Int = 14,
        swingPeriod: Int = 5
    ): Result<MarketAnalysisResponse>
}

























