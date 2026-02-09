package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Portfolio Risk Status DTO
 */
data class PortfolioRiskStatusDto(
    @SerializedName("status")
    val status: String,
    @SerializedName("total_exposure")
    val totalExposure: Double? = null,
    @SerializedName("total_pnl")
    val totalPnL: Double? = null,
    @SerializedName("max_drawdown")
    val maxDrawdown: Double? = null,
    @SerializedName("daily_loss")
    val dailyLoss: Double? = null,
    @SerializedName("weekly_loss")
    val weeklyLoss: Double? = null,
    @SerializedName("account_id")
    val accountId: String? = null
)

/**
 * Risk Management Configuration DTO
 */
data class RiskManagementConfigDto(
    @SerializedName("id")
    val id: String? = null,
    @SerializedName("account_id")
    val accountId: String? = null,
    @SerializedName("max_portfolio_exposure")
    val maxPortfolioExposure: Double? = null,
    @SerializedName("max_daily_loss")
    val maxDailyLoss: Double? = null,
    @SerializedName("max_weekly_loss")
    val maxWeeklyLoss: Double? = null,
    @SerializedName("max_drawdown_pct")
    val maxDrawdownPct: Double? = null,
    @SerializedName("circuit_breaker_enabled")
    val circuitBreakerEnabled: Boolean = false,
    @SerializedName("max_consecutive_losses")
    val maxConsecutiveLosses: Int? = null,
    @SerializedName("rapid_loss_threshold_pct")
    val rapidLossThresholdPct: Double? = null,
    @SerializedName("rapid_loss_timeframe_minutes")
    val rapidLossTimeframeMinutes: Int? = null,
    @SerializedName("circuit_breaker_cooldown_minutes")
    val circuitBreakerCooldownMinutes: Int? = null
)
