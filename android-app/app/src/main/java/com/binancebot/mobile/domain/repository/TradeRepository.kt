package com.binancebot.mobile.domain.repository

import androidx.paging.PagingData
import com.binancebot.mobile.domain.model.Trade
import kotlinx.coroutines.flow.Flow

/**
 * Repository interface for Trade operations.
 * ✅ Uses Paging 3 for efficient pagination.
 */
interface TradeRepository {
    fun getTrades(
        strategyId: String? = null,
        symbol: String? = null,
        dateFrom: String? = null,
        dateTo: String? = null
    ): Flow<PagingData<Trade>>
    fun getTradesByStrategy(strategyId: String): Flow<List<Trade>>
}








