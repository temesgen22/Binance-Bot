package com.binancebot.mobile.data.remote.paging

import android.util.Log
import androidx.paging.PagingSource
import androidx.paging.PagingState
import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.TradeDto
import com.binancebot.mobile.domain.model.Trade

/**
 * PagingSource for Trade pagination
 */
class TradePagingSource(
    private val api: BinanceBotApi,
    private val filters: TradeFilters
) : PagingSource<Int, Trade>() {
    
    override suspend fun load(params: LoadParams<Int>): LoadResult<Int, Trade> {
        return try {
            val page = params.key ?: 0
            val pageSize = params.loadSize
            
            val response = api.getTrades(
                strategyId = filters.strategyId,
                symbol = filters.symbol,
                side = filters.side,
                startDate = filters.dateFrom,
                endDate = filters.dateTo,
                limit = pageSize,
                offset = page * pageSize
            )
            
            if (response.isSuccessful && response.body() != null) {
                val trades = response.body()!!
                    .mapNotNull { dto ->
                        try {
                            dto.toDomain()
                        } catch (e: Exception) {
                            // Log error but don't crash - skip invalid trades
                            Log.e("TradePagingSource", "Failed to convert trade DTO: ${e.message}", e)
                            null
                        }
                    }
                val nextKey = if (trades.size < pageSize) null else page + 1
                val prevKey = if (page > 0) page - 1 else null
                
                LoadResult.Page(
                    data = trades,
                    prevKey = prevKey,
                    nextKey = nextKey
                )
            } else {
                LoadResult.Error(Exception("Failed to load trades: ${response.message()}"))
            }
        } catch (e: Exception) {
            LoadResult.Error(e)
        }
    }
    
    override fun getRefreshKey(state: PagingState<Int, Trade>): Int? {
        return state.anchorPosition?.let { anchorPosition ->
            val anchorPage = state.closestPageToPosition(anchorPosition)
            anchorPage?.prevKey?.plus(1) ?: anchorPage?.nextKey?.minus(1)
        }
    }
}

/**
 * Filters for Trade pagination
 */
data class TradeFilters(
    val strategyId: String? = null,
    val symbol: String? = null,
    val side: String? = null,
    val dateFrom: String? = null,
    val dateTo: String? = null
)

// Extension to convert DTO to domain
private fun com.binancebot.mobile.data.remote.dto.TradeDto.toDomain(): Trade {
    // Generate fallback ID if null (using orderId or UUID)
    val tradeId = id ?: orderId?.toString() ?: java.util.UUID.randomUUID().toString()
    
    // Validate required fields and provide defaults
    val tradeStrategyId = strategyId ?: "unknown"
    val tradeOrderId = orderId ?: 0L
    val tradeSymbol = symbol ?: "UNKNOWN"
    val tradeSide = side ?: "UNKNOWN"
    val tradeExecutedQty = executedQty ?: 0.0
    val tradeAvgPrice = avgPrice ?: 0.0
    
    // Convert timestamp string to Long (milliseconds)
    val timestampLong = timestamp?.let {
        try {
            java.time.Instant.parse(it).toEpochMilli()
        } catch (e: Exception) {
            System.currentTimeMillis()
        }
    } ?: System.currentTimeMillis()
    
    return Trade(
        id = tradeId,
        strategyId = tradeStrategyId,
        orderId = tradeOrderId,
        symbol = tradeSymbol,
        side = tradeSide,
        executedQty = tradeExecutedQty,
        avgPrice = tradeAvgPrice,
        commission = commission,
        timestamp = timestampLong,
        positionSide = positionSide,
        exitReason = exitReason
    )
}
