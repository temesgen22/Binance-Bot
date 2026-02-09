package com.binancebot.mobile.data.local.entities

import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.Index

/**
 * Room entity for Trade.
 * Maps to domain model Trade.
 */
@Entity(
    tableName = "trades",
    indices = [
        Index(value = ["strategyId"]),
        Index(value = ["orderId"], unique = true),
        Index(value = ["timestamp"])
    ]
)
data class TradeEntity(
    @PrimaryKey val id: String,
    val strategyId: String,
    val orderId: Long,
    val symbol: String,
    val side: String,
    val executedQty: Double,
    val avgPrice: Double,
    val commission: Double? = null,
    val timestamp: Long,
    val positionSide: String? = null,
    val exitReason: String? = null
) {
    fun toDomain(): com.binancebot.mobile.domain.model.Trade {
        return com.binancebot.mobile.domain.model.Trade(
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
    
    companion object {
        fun fromDomain(trade: com.binancebot.mobile.domain.model.Trade): TradeEntity {
            return TradeEntity(
                id = trade.id,
                strategyId = trade.strategyId,
                orderId = trade.orderId,
                symbol = trade.symbol,
                side = trade.side,
                executedQty = trade.executedQty,
                avgPrice = trade.avgPrice,
                commission = trade.commission,
                timestamp = trade.timestamp,
                positionSide = trade.positionSide,
                exitReason = trade.exitReason
            )
        }
    }
}
































