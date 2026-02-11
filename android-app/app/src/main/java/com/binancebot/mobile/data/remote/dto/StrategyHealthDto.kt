package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

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





