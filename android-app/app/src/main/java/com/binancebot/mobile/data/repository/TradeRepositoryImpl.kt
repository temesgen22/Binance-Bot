package com.binancebot.mobile.data.repository

import androidx.paging.Pager
import androidx.paging.PagingConfig
import androidx.paging.PagingData
import com.binancebot.mobile.data.local.dao.TradeDao
import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.paging.TradePagingSource
import com.binancebot.mobile.domain.model.Trade
import com.binancebot.mobile.domain.model.SymbolPnL
import com.binancebot.mobile.data.remote.dto.ManualCloseRequestDto
import com.binancebot.mobile.data.remote.dto.ManualOpenRequestDto
import com.binancebot.mobile.data.remote.dto.ManualPositionCloseRequestDto
import com.binancebot.mobile.domain.model.Position
import com.binancebot.mobile.domain.repository.TradeRepository
import com.binancebot.mobile.domain.repository.ManualOpenResult
import com.binancebot.mobile.domain.repository.ManualCloseResult
import com.binancebot.mobile.domain.repository.ManualPositionInfo
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
        dateTo: String?,
        accountId: String?
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
                        dateTo = dateTo,
                        accountId = accountId
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

    override suspend fun manualClosePosition(
        strategyId: String,
        symbol: String?,
        positionSide: String?
    ): Result<Unit> {
        return try {
            val request = ManualCloseRequestDto(symbol = symbol, positionSide = positionSide)
            val response = api.manualClosePosition(strategyId, request)
            if (response.isSuccessful) {
                Result.success(Unit)
            } else {
                val body = response.errorBody()?.string()
                val msg = body?.takeIf { it.isNotBlank() } ?: response.message() ?: "Manual close failed"
                Result.failure(Exception(msg))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    // ========== Manual Trading ==========
    
    override suspend fun openManualPosition(
        symbol: String,
        side: String,
        usdtAmount: Double,
        accountId: String,
        leverage: Int,
        marginType: String?,
        takeProfitPct: Double?,
        stopLossPct: Double?,
        tpPrice: Double?,
        slPrice: Double?,
        trailingStopEnabled: Boolean,
        trailingStopCallbackRate: Double?,
        notes: String?
    ): Result<ManualOpenResult> {
        return try {
            val request = ManualOpenRequestDto(
                symbol = symbol,
                side = side,
                usdtAmount = usdtAmount,
                accountId = accountId,
                leverage = leverage,
                marginType = marginType,
                takeProfitPct = takeProfitPct,
                stopLossPct = stopLossPct,
                tpPrice = tpPrice,
                slPrice = slPrice,
                trailingStopEnabled = trailingStopEnabled,
                trailingStopCallbackRate = trailingStopCallbackRate,
                notes = notes
            )
            val response = api.openManualPosition(request)
            if (response.isSuccessful && response.body() != null) {
                val dto = response.body()!!
                Result.success(
                    ManualOpenResult(
                        positionId = dto.positionId,
                        entryOrderId = dto.entryOrderId,
                        symbol = dto.symbol,
                        side = dto.side,
                        quantity = dto.quantity,
                        entryPrice = dto.entryPrice,
                        leverage = dto.leverage,
                        tpOrderId = dto.tpOrderId,
                        tpPrice = dto.tpPrice,
                        slOrderId = dto.slOrderId,
                        slPrice = dto.slPrice,
                        trailingStopEnabled = dto.trailingStopEnabled
                    )
                )
            } else {
                val body = response.errorBody()?.string()
                val msg = body?.takeIf { it.isNotBlank() } ?: response.message() ?: "Failed to open position"
                Result.failure(Exception(msg))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun closeManualPosition(
        positionId: String,
        quantity: Double?
    ): Result<ManualCloseResult> {
        return try {
            val request = ManualPositionCloseRequestDto(
                positionId = positionId,
                quantity = quantity
            )
            val response = api.closeManualPosition(request)
            if (response.isSuccessful && response.body() != null) {
                val dto = response.body()!!
                Result.success(
                    ManualCloseResult(
                        positionId = dto.positionId,
                        exitOrderId = dto.exitOrderId,
                        symbol = dto.symbol,
                        side = dto.side,
                        closedQuantity = dto.closedQuantity,
                        remainingQuantity = dto.remainingQuantity,
                        exitPrice = dto.exitPrice,
                        realizedPnl = dto.realizedPnl,
                        feePaid = dto.feePaid
                    )
                )
            } else {
                val body = response.errorBody()?.string()
                val msg = body?.takeIf { it.isNotBlank() } ?: response.message() ?: "Failed to close position"
                Result.failure(Exception(msg))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun getManualPositions(
        status: String?,
        accountId: String?,
        symbol: String?
    ): Result<List<ManualPositionInfo>> {
        return try {
            val response = api.getManualPositions(status, accountId, symbol)
            if (response.isSuccessful && response.body() != null) {
                val dto = response.body()!!
                Result.success(dto.positions.map { pos ->
                    ManualPositionInfo(
                        id = pos.id,
                        symbol = pos.symbol,
                        side = pos.side,
                        quantity = pos.quantity,
                        remainingQuantity = pos.remainingQuantity,
                        entryPrice = pos.entryPrice,
                        leverage = pos.leverage,
                        status = pos.status,
                        tpPrice = pos.tpPrice,
                        slPrice = pos.slPrice,
                        currentPrice = pos.currentPrice,
                        unrealizedPnl = pos.unrealizedPnl,
                        realizedPnl = pos.realizedPnl,
                        createdAt = pos.createdAt
                    )
                })
            } else {
                val body = response.errorBody()?.string()
                val msg = body?.takeIf { it.isNotBlank() } ?: response.message() ?: "Failed to get positions"
                Result.failure(Exception(msg))
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
        maxUnrealizedPnL = maxUnrealizedPnL,
        leverage = leverage,
        strategyId = strategyId,
        strategyName = strategyName,
        accountId = accountId,
        liquidationPrice = liquidationPrice,
        initialMargin = initialMargin,
        marginType = marginType
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

