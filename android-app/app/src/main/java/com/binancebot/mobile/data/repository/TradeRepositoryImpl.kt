package com.binancebot.mobile.data.repository

import androidx.paging.Pager
import androidx.paging.PagingConfig
import androidx.paging.PagingData
import com.binancebot.mobile.data.local.dao.TradeDao
import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.paging.TradePagingSource
import com.binancebot.mobile.domain.model.Trade
import com.binancebot.mobile.domain.model.SymbolPnL
import com.binancebot.mobile.domain.model.Position
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
        side: String?,
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
                        side = side,
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
    
    override suspend fun getPnLOverview(
        accountId: String?,
        startDate: String?,
        endDate: String?
    ): Result<List<SymbolPnL>> {
        return try {
            val response = api.getPnLOverview(
                accountId = accountId,
                startDate = startDate,
                endDate = endDate
            )
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!.map { it.toDomain() })
            } else {
                Result.failure(Exception("Failed to load PnL overview: ${response.message()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun getSymbols(): Result<List<String>> {
        return try {
            val response = api.getSymbols()
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception("Failed to load symbols: ${response.message()}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}

// Extension to convert DTO to domain
private fun com.binancebot.mobile.data.remote.dto.PositionSummaryDto.toDomain(): Position {
    return Position(
        symbol = symbol,
        positionSize = positionSize,
        entryPrice = entryPrice,
        currentPrice = currentPrice,
        positionSide = positionSide,
        unrealizedPnL = unrealizedPnL,
        leverage = leverage,
        strategyId = strategyId,
        strategyName = strategyName
    )
}

private fun com.binancebot.mobile.data.remote.dto.SymbolPnLDto.toDomain(): SymbolPnL {
    return SymbolPnL(
        symbol = this.symbol,
        totalRealizedPnL = this.totalRealizedPnL,
        totalUnrealizedPnL = this.totalUnrealizedPnL,
        totalPnL = this.totalPnL,
        openPositions = this.openPositions.map { it.toDomain() },
        totalTrades = this.totalTrades,
        completedTrades = this.completedTrades,
        winRate = this.winRate,
        winningTrades = this.winningTrades,
        losingTrades = this.losingTrades,
        totalTradeFees = this.totalTradeFees,
        totalFundingFees = this.totalFundingFees
    )
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

