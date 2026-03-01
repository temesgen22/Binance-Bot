package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Reason why the strategy did not execute an order (from backend health API).
 * Shown in strategy detail / execution health status when present.
 */
data class OrderFailureDto(
    @SerializedName("reason")
    val reason: String? = null,
    @SerializedName("at")
    val at: String? = null,
    @SerializedName("error_type")
    val errorType: String? = null
)

/**
 * Strategy Health Status DTO
 */
data class StrategyHealthDto(
    @SerializedName("strategy_id")
    val strategyId: String? = null,
    @SerializedName("strategy_name")
    val strategyName: String? = null,
    @SerializedName("status")
    val status: String? = null,
    @SerializedName("health_status")
    val healthStatus: String? = null, // "healthy", "execution_stale", "task_dead", "no_execution_tracking", "no_recent_orders"
    @SerializedName("is_healthy")
    val isHealthy: Boolean? = null,
    @SerializedName("issues")
    val issues: List<String>? = null,
    @SerializedName("task_status")
    val taskStatus: Map<String, Any?>? = null,
    @SerializedName("execution_status")
    val executionStatus: Map<String, Any?>? = null,
    @SerializedName("order_status")
    val orderStatus: Map<String, Any?>? = null,
    /** When set, strategy is not executing orders; reason explains why (e.g. insufficient balance, timeout). */
    @SerializedName("order_failure")
    val orderFailure: OrderFailureDto? = null,
    @SerializedName("meta")
    val meta: Map<String, Any?>? = null
)

/**
 * Strategy Risk Status DTO
 */
data class StrategyRiskStatusDto(
    @SerializedName("strategy_id")
    val strategyId: String? = null,
    @SerializedName("account_id")
    val accountId: String? = null,
    @SerializedName("can_trade")
    val canTrade: Boolean? = null,
    @SerializedName("blocked_reasons")
    val blockedReasons: List<String>? = null,
    @SerializedName("circuit_breaker_active")
    val circuitBreakerActive: Boolean? = null,
    @SerializedName("risk_checks")
    val riskChecks: Map<String, Any?>? = null,
    @SerializedName("last_enforcement_event")
    val lastEnforcementEvent: Map<String, Any?>? = null
)





