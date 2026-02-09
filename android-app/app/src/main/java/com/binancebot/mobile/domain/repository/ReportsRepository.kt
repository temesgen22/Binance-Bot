package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.TradingReportDto

interface ReportsRepository {
    suspend fun getTradingReport(
        strategyId: String? = null,
        strategyName: String? = null,
        symbol: String? = null,
        startDate: String? = null,
        endDate: String? = null,
        accountId: String? = null
    ): Result<TradingReportDto>
}



























