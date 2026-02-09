package com.binancebot.mobile.data.repository

import androidx.paging.Pager
import androidx.paging.PagingConfig
import androidx.paging.PagingData
import com.binancebot.mobile.data.local.dao.TradeDao
import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.paging.TradePagingSource
import com.binancebot.mobile.domain.model.Trade
import com.binancebot.mobile.domain.repository.TradeRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Trade Repository Implementation.
 * ✅ Uses Paging 3 for efficient pagination.
 */
@Singleton
class TradeRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi,
    private val dao: TradeDao
) : TradeRepository {
    
    override fun getTrades(
        strategyId: String?,
        symbol: String?,
        dateFrom: String?,
        dateTo: String?
    ): Flow<PagingData<Trade>> {
        return Pager(
            config = PagingConfig(
                pageSize = 20,
                enablePlaceholders = false,
                initialLoadSize = 40
            ),
            pagingSourceFactory = {
                TradePagingSource(
                    api,
                    com.binancebot.mobile.data.remote.paging.TradeFilters(
                        strategyId = strategyId,
                        symbol = symbol,
                        dateFrom = dateFrom,
                        dateTo = dateTo
                    )
                )
            }
        ).flow
    }
    
    override fun getTradesByStrategy(strategyId: String): Flow<List<Trade>> {
        return dao.getTradesByStrategy(strategyId)
            .map { entities -> entities.map { it.toDomain() } }
            .flowOn(Dispatchers.IO)
    }
}

// Extension to convert entity to domain
private fun com.binancebot.mobile.data.local.entities.TradeEntity.toDomain(): Trade {
    return Trade(
        id = id,
        strategyId = strategyId,
        orderId = orderId,
        symbol = symbol,
        side = side,
        executedQty = executedQty,
        avgPrice = avgPrice,
        commission = commission,
        timestamp = timestamp,
        positionSide = positionSide,
        exitReason = exitReason
    )
}

