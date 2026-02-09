package com.binancebot.mobile.domain.repository

import androidx.paging.PagingData
import com.binancebot.mobile.domain.model.Trade
import com.binancebot.mobile.domain.model.SymbolPnL
import kotlinx.coroutines.flow.Flow

/**
 * Repository interface for Trade operations.
 * ✅ Uses Paging 3 for efficient pagination.
 */
interface TradeRepository {
    fun getTrades(
        strategyId: String? = null,
        symbol: String? = null,
        side: String? = null,
        dateFrom: String? = null,
        dateTo: String? = null
    ): Flow<PagingData<Trade>>
    fun getTradesByStrategy(strategyId: String): Flow<List<Trade>>
    suspend fun getPnLOverview(
        accountId: String? = null,
        startDate: String? = null,
        endDate: String? = null
    ): Result<List<SymbolPnL>>
    suspend fun getSymbols(): Result<List<String>>
}








