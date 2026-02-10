package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Portfolio Risk Status DTO
 */
data class PortfolioRiskStatusDto(
    @SerializedName("risk_status")
    val status: String? = null,
    @SerializedName("total_exposure_usdt")
    val totalExposure: Double? = null,
    @SerializedName("total_exposure_pct")
    val totalExposurePct: Double? = null,
    @SerializedName("daily_pnl_usdt")
    val dailyPnL: Double? = null,
    @SerializedName("daily_pnl_pct")
    val dailyPnLPct: Double? = null,
    @SerializedName("weekly_pnl_usdt")
    val weeklyPnL: Double? = null,
    @SerializedName("weekly_pnl_pct")
    val weeklyPnLPct: Double? = null,
    @SerializedName("current_drawdown_pct")
    val currentDrawdownPct: Double? = null,
    @SerializedName("max_drawdown_pct")
    val maxDrawdownPct: Double? = null,
    @SerializedName("max_drawdown_limit_pct")
    val maxDrawdownLimitPct: Double? = null,
    @SerializedName("account_id")
    val accountId: String? = null,
    @SerializedName("active_circuit_breakers")
    val activeCircuitBreakers: List<String>? = null,
    @SerializedName("warnings")
    val warnings: List<String>? = null
)

/**
 * Risk Management Configuration DTO
 */
data class RiskManagementConfigDto(
    @SerializedName("id")
    val id: String? = null,
    @SerializedName("user_id")
    val userId: String? = null,
    @SerializedName("account_id")
    val accountId: String? = null,
    // Portfolio Limits
    @SerializedName("max_portfolio_exposure_usdt")
    val maxPortfolioExposureUsdt: Double? = null,
    @SerializedName("max_portfolio_exposure_pct")
    val maxPortfolioExposurePct: Double? = null,
    @SerializedName("max_daily_loss_usdt")
    val maxDailyLossUsdt: Double? = null,
    @SerializedName("max_daily_loss_pct")
    val maxDailyLossPct: Double? = null,
    @SerializedName("max_weekly_loss_usdt")
    val maxWeeklyLossUsdt: Double? = null,
    @SerializedName("max_weekly_loss_pct")
    val maxWeeklyLossPct: Double? = null,
    @SerializedName("max_drawdown_pct")
    val maxDrawdownPct: Double? = null,
    // Loss Reset Configuration
    @SerializedName("daily_loss_reset_time")
    val dailyLossResetTime: String? = null,
    @SerializedName("weekly_loss_reset_day")
    val weeklyLossResetDay: Int? = null,
    @SerializedName("timezone")
    val timezone: String? = "UTC",
    // Circuit Breaker Settings
    @SerializedName("circuit_breaker_enabled")
    val circuitBreakerEnabled: Boolean = false,
    @SerializedName("max_consecutive_losses")
    val maxConsecutiveLosses: Int? = null,
    @SerializedName("rapid_loss_threshold_pct")
    val rapidLossThresholdPct: Double? = null,
    @SerializedName("rapid_loss_timeframe_minutes")
    val rapidLossTimeframeMinutes: Int? = null,
    @SerializedName("circuit_breaker_cooldown_minutes")
    val circuitBreakerCooldownMinutes: Int? = null,
    // Dynamic Risk Settings
    @SerializedName("volatility_based_sizing_enabled")
    val volatilityBasedSizingEnabled: Boolean = false,
    @SerializedName("performance_based_adjustment_enabled")
    val performanceBasedAdjustmentEnabled: Boolean = false,
    @SerializedName("kelly_criterion_enabled")
    val kellyCriterionEnabled: Boolean = false,
    @SerializedName("kelly_fraction")
    val kellyFraction: Double? = null,
    // Correlation Limits
    @SerializedName("correlation_limits_enabled")
    val correlationLimitsEnabled: Boolean = false,
    @SerializedName("max_correlation_exposure_pct")
    val maxCorrelationExposurePct: Double? = null,
    // Margin Protection
    @SerializedName("margin_call_protection_enabled")
    val marginCallProtectionEnabled: Boolean = true,
    @SerializedName("min_margin_ratio")
    val minMarginRatio: Double? = null,
    // Trade Frequency Limits
    @SerializedName("max_trades_per_day_per_strategy")
    val maxTradesPerDayPerStrategy: Int? = null,
    @SerializedName("max_trades_per_day_total")
    val maxTradesPerDayTotal: Int? = null,
    // Order Size Adjustment
    @SerializedName("auto_reduce_order_size")
    val autoReduceOrderSize: Boolean = false,
    // Legacy fields for backward compatibility
    @SerializedName("max_portfolio_exposure")
    val maxPortfolioExposure: Double? = null,
    @SerializedName("max_daily_loss")
    val maxDailyLoss: Double? = null,
    @SerializedName("max_weekly_loss")
    val maxWeeklyLoss: Double? = null,
    @SerializedName("created_at")
    val createdAt: String? = null,
    @SerializedName("updated_at")
    val updatedAt: String? = null
)

/**
 * Portfolio Risk Metrics DTO
 */
data class PortfolioRiskMetricsDto(
    @SerializedName("id")
    val id: String? = null,
    @SerializedName("account_id")
    val accountId: String? = null,
    @SerializedName("timestamp")
    val timestamp: String? = null,
    // Balance Tracking
    @SerializedName("total_balance_usdt")
    val totalBalanceUsdt: Double? = null,
    @SerializedName("available_balance_usdt")
    val availableBalanceUsdt: Double? = null,
    @SerializedName("used_margin_usdt")
    val usedMarginUsdt: Double? = null,
    @SerializedName("peak_balance_usdt")
    val peakBalanceUsdt: Double? = null,
    // Portfolio Metrics
    @SerializedName("total_exposure_usdt")
    val totalExposureUsdt: Double? = null,
    @SerializedName("total_exposure_pct")
    val totalExposurePct: Double? = null,
    @SerializedName("daily_pnl_usdt")
    val dailyPnLUsdt: Double? = null,
    @SerializedName("daily_pnl_pct")
    val dailyPnLPct: Double? = null,
    @SerializedName("weekly_pnl_usdt")
    val weeklyPnLUsdt: Double? = null,
    @SerializedName("weekly_pnl_pct")
    val weeklyPnLPct: Double? = null,
    @SerializedName("current_drawdown_pct")
    val currentDrawdownPct: Double? = null,
    @SerializedName("max_drawdown_pct")
    val maxDrawdownPct: Double? = null,
    // Performance Metrics
    @SerializedName("sharpe_ratio")
    val sharpeRatio: Double? = null,
    @SerializedName("profit_factor")
    val profitFactor: Double? = null,
    @SerializedName("win_rate")
    val winRate: Double? = null,
    @SerializedName("avg_win")
    val avgWin: Double? = null,
    @SerializedName("avg_loss")
    val avgLoss: Double? = null,
    @SerializedName("total_trades")
    val totalTrades: Int? = null,
    @SerializedName("winning_trades")
    val winningTrades: Int? = null,
    @SerializedName("losing_trades")
    val losingTrades: Int? = null
)

/**
 * Strategy Risk Metrics DTO
 */
data class StrategyRiskMetricsDto(
    @SerializedName("strategy_id")
    val strategyId: String,
    @SerializedName("strategy_name")
    val strategyName: String? = null,
    @SerializedName("symbol")
    val symbol: String? = null,
    @SerializedName("metrics")
    val metrics: PortfolioRiskMetricsDto? = null,
    @SerializedName("message")
    val message: String? = null
)

/**
 * Enforcement Event DTO
 */
data class EnforcementEventDto(
    @SerializedName("id")
    val id: String,
    @SerializedName("event_type")
    val eventType: String,
    @SerializedName("event_level")
    val eventLevel: String,
    @SerializedName("message")
    val message: String,
    @SerializedName("strategy_id")
    val strategyId: String? = null,
    @SerializedName("account_id")
    val accountId: String? = null,
    @SerializedName("event_metadata")
    val eventMetadata: Map<String, Any>? = null,
    @SerializedName("created_at")
    val createdAt: String
)

/**
 * Enforcement History DTO
 */
data class EnforcementHistoryDto(
    @SerializedName("events")
    val events: List<EnforcementEventDto>,
    @SerializedName("total")
    val total: Int,
    @SerializedName("limit")
    val limit: Int,
    @SerializedName("offset")
    val offset: Int
)

/**
 * Risk Report DTO
 */
data class RiskReportDto(
    @SerializedName("date")
    val date: String? = null,
    @SerializedName("week_start")
    val weekStart: String? = null,
    @SerializedName("week_end")
    val weekEnd: String? = null,
    @SerializedName("total_trades")
    val totalTrades: Int? = null,
    @SerializedName("win_rate")
    val winRate: Double? = null,
    @SerializedName("total_pnl")
    val totalPnL: Double? = null,
    @SerializedName("profit_factor")
    val profitFactor: Double? = null,
    @SerializedName("max_drawdown_pct")
    val maxDrawdownPct: Double? = null,
    @SerializedName("sharpe_ratio")
    val sharpeRatio: Double? = null,
    @SerializedName("daily_loss")
    val dailyLoss: Double? = null,
    @SerializedName("weekly_loss")
    val weeklyLoss: Double? = null
)

/**
 * Strategy Risk Config DTO
 */
data class StrategyRiskConfigDto(
    @SerializedName("id")
    val id: String? = null,
    @SerializedName("strategy_id")
    val strategyId: String,
    @SerializedName("enabled")
    val enabled: Boolean = true,
    @SerializedName("max_daily_loss_usdt")
    val maxDailyLossUsdt: Double? = null,
    @SerializedName("max_daily_loss_pct")
    val maxDailyLossPct: Double? = null,
    @SerializedName("max_weekly_loss_usdt")
    val maxWeeklyLossUsdt: Double? = null,
    @SerializedName("max_weekly_loss_pct")
    val maxWeeklyLossPct: Double? = null,
    @SerializedName("max_drawdown_pct")
    val maxDrawdownPct: Double? = null,
    @SerializedName("override_account_limits")
    val overrideAccountLimits: Boolean = false,
    @SerializedName("use_more_restrictive")
    val useMoreRestrictive: Boolean = true,
    @SerializedName("created_at")
    val createdAt: String? = null,
    @SerializedName("updated_at")
    val updatedAt: String? = null
)
