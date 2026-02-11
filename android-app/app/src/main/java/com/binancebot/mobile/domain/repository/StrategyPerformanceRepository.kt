package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.StrategyPerformanceDto
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceListDto

interface StrategyPerformanceRepository {
    suspend fun getStrategyPerformance(
        strategyName: String? = null,
        symbol: String? = null,
        status: String? = null,
        rankBy: String? = "total_pnl",
        startDate: String? = null,
        endDate: String? = null,
        accountId: String? = null
    ): Result<StrategyPerformanceListDto>
    
    suspend fun getStrategyPerformanceById(strategyId: String): Result<StrategyPerformanceDto>
}





































