package com.binancebot.mobile.data.local.entities

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Room entity for Strategy.
 * Maps to domain model Strategy.
 */
@Entity(tableName = "strategies")
data class StrategyEntity(
    @PrimaryKey val id: String,
    val name: String,
    val symbol: String,
    val strategyType: String,
    val status: String,
    val leverage: Int,
    val riskPerTrade: Double? = null,
    val fixedAmount: Double? = null,
    val accountId: String,
    val positionSide: String? = null,
    val positionSize: Double? = null,
    val entryPrice: Double? = null,
    val currentPrice: Double? = null,
    val unrealizedPnL: Double? = null,
    val lastSignal: String? = null,
    val lastUpdated: Long = System.currentTimeMillis()
) {
    fun toDomain(): com.binancebot.mobile.domain.model.Strategy {
        return com.binancebot.mobile.domain.model.Strategy(
            id = id,
            name = name,
            symbol = symbol,
            strategyType = strategyType,
            status = status,
            leverage = leverage,
            riskPerTrade = riskPerTrade,
            fixedAmount = fixedAmount,
            accountId = accountId,
            positionSide = positionSide,
            positionSize = positionSize,
            entryPrice = entryPrice,
            currentPrice = currentPrice,
            unrealizedPnL = unrealizedPnL,
            lastSignal = lastSignal
        )
    }
    
    companion object {
        fun fromDomain(strategy: com.binancebot.mobile.domain.model.Strategy): StrategyEntity {
            return StrategyEntity(
                id = strategy.id,
                name = strategy.name,
                symbol = strategy.symbol,
                strategyType = strategy.strategyType,
                status = strategy.status,
                leverage = strategy.leverage,
                riskPerTrade = strategy.riskPerTrade,
                fixedAmount = strategy.fixedAmount,
                accountId = strategy.accountId,
                positionSide = strategy.positionSide,
                positionSize = strategy.positionSize,
                entryPrice = strategy.entryPrice,
                currentPrice = strategy.currentPrice,
                unrealizedPnL = strategy.unrealizedPnL,
                lastSignal = strategy.lastSignal
            )
        }
    }
}












































