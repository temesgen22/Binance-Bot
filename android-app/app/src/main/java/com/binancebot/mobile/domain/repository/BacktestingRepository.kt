package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.BacktestRequestDto
import com.binancebot.mobile.data.remote.dto.BacktestResultDto

/**
 * Repository interface for Backtesting operations.
 */
interface BacktestingRepository {
    suspend fun runBacktest(request: BacktestRequestDto): Result<BacktestResultDto>
}



