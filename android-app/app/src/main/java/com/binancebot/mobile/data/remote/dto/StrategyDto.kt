package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

data class StrategyDto(
    @SerializedName("id")
    val id: String,
    @SerializedName("name")
    val name: String,
    @SerializedName("symbol")
    val symbol: String,
    @SerializedName("strategy_type")
    val strategyType: String,
    @SerializedName("status")
    val status: String,
    @SerializedName("leverage")
    val leverage: Int,
    @SerializedName("risk_per_trade")
    val riskPerTrade: Double? = null,  // Backend requires, but nullable for safety
    @SerializedName("fixed_amount")
    val fixedAmount: Double? = null,
    @SerializedName("params")
    val params: Map<String, Any>? = null,  // Backend returns StrategyParams as dict
    @SerializedName("account_id")
    val accountId: String = "default",  // Default if missing
    @SerializedName("created_at")
    val createdAt: String? = null,  // Backend requires, but make nullable for safety
    @SerializedName("last_signal")
    val lastSignal: String? = null,  // "BUY", "SELL", or "HOLD"
    @SerializedName("entry_price")
    val entryPrice: Double? = null,
    @SerializedName("current_price")
    val currentPrice: Double? = null,
    @SerializedName("position_size")
    val positionSize: Double? = null,
    @SerializedName("position_side")
    val positionSide: String? = null,  // "LONG" or "SHORT"
    @SerializedName("unrealized_pnl")
    val unrealizedPnl: Double? = null,
    @SerializedName("position_instance_id")
    val positionInstanceId: String? = null,  // UUID as string
    @SerializedName("started_at")
    val startedAt: String? = null,  // ISO datetime string
    @SerializedName("stopped_at")
    val stoppedAt: String? = null,  // ISO datetime string
    @SerializedName("meta")
    val meta: Map<String, Any>? = null,  // Additional metadata
    @SerializedName("auto_tuning_enabled")
    val autoTuningEnabled: Boolean = false
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
            unrealizedPnL = unrealizedPnl,
            lastSignal = lastSignal
        )
    }
}










