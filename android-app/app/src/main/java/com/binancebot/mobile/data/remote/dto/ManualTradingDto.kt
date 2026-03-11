package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * Request to open a manual position
 */
data class ManualOpenRequestDto(
    val symbol: String,
    val side: String, // "LONG" or "SHORT"
    @SerializedName("usdt_amount") val usdtAmount: Double,
    @SerializedName("account_id") val accountId: String = "default",
    val leverage: Int = 10,
    @SerializedName("margin_type") val marginType: String? = "CROSSED",
    @SerializedName("take_profit_pct") val takeProfitPct: Double? = null,
    @SerializedName("stop_loss_pct") val stopLossPct: Double? = null,
    @SerializedName("tp_price") val tpPrice: Double? = null,
    @SerializedName("sl_price") val slPrice: Double? = null,
    @SerializedName("trailing_stop_enabled") val trailingStopEnabled: Boolean = false,
    @SerializedName("trailing_stop_callback_rate") val trailingStopCallbackRate: Double? = null,
    val notes: String? = null
)

/**
 * Response after opening a manual position
 */
data class ManualOpenResponseDto(
    @SerializedName("position_id") val positionId: String,
    @SerializedName("entry_order_id") val entryOrderId: Long,
    val symbol: String,
    val side: String,
    val quantity: Double,
    @SerializedName("entry_price") val entryPrice: Double,
    val leverage: Int,
    @SerializedName("margin_type") val marginType: String,
    @SerializedName("tp_order_id") val tpOrderId: Long? = null,
    @SerializedName("tp_price") val tpPrice: Double? = null,
    @SerializedName("sl_order_id") val slOrderId: Long? = null,
    @SerializedName("sl_price") val slPrice: Double? = null,
    @SerializedName("trailing_stop_enabled") val trailingStopEnabled: Boolean = false,
    @SerializedName("initial_margin") val initialMargin: Double? = null,
    @SerializedName("liquidation_price") val liquidationPrice: Double? = null,
    @SerializedName("paper_trading") val paperTrading: Boolean = false,
    @SerializedName("created_at") val createdAt: String
)

/**
 * Request to close a manual position
 */
data class ManualPositionCloseRequestDto(
    @SerializedName("position_id") val positionId: String,
    val quantity: Double? = null // null = full close
)

/**
 * Response after closing a manual position
 */
data class ManualPositionCloseResponseDto(
    @SerializedName("position_id") val positionId: String,
    @SerializedName("exit_order_id") val exitOrderId: Long,
    val symbol: String,
    val side: String,
    @SerializedName("closed_quantity") val closedQuantity: Double,
    @SerializedName("remaining_quantity") val remainingQuantity: Double,
    @SerializedName("exit_price") val exitPrice: Double,
    @SerializedName("realized_pnl") val realizedPnl: Double,
    @SerializedName("fee_paid") val feePaid: Double,
    @SerializedName("exit_reason") val exitReason: String,
    @SerializedName("closed_at") val closedAt: String
)

/**
 * Request to modify TP/SL on a manual position
 */
data class ManualModifyTpSlRequestDto(
    @SerializedName("position_id") val positionId: String,
    @SerializedName("take_profit_pct") val takeProfitPct: Double? = null,
    @SerializedName("stop_loss_pct") val stopLossPct: Double? = null,
    @SerializedName("tp_price") val tpPrice: Double? = null,
    @SerializedName("sl_price") val slPrice: Double? = null,
    @SerializedName("cancel_tp") val cancelTp: Boolean = false,
    @SerializedName("cancel_sl") val cancelSl: Boolean = false,
    @SerializedName("trailing_stop_enabled") val trailingStopEnabled: Boolean? = null,
    @SerializedName("trailing_stop_callback_rate") val trailingStopCallbackRate: Double? = null
)

/**
 * Response after modifying TP/SL
 */
data class ManualModifyResponseDto(
    @SerializedName("position_id") val positionId: String,
    val symbol: String,
    @SerializedName("tp_order_id") val tpOrderId: Long? = null,
    @SerializedName("tp_price") val tpPrice: Double? = null,
    @SerializedName("sl_order_id") val slOrderId: Long? = null,
    @SerializedName("sl_price") val slPrice: Double? = null,
    @SerializedName("trailing_stop_enabled") val trailingStopEnabled: Boolean = false,
    @SerializedName("cancelled_orders") val cancelledOrders: List<Long> = emptyList()
)

/**
 * Single manual position details
 */
data class ManualPositionResponseDto(
    val id: String,
    @SerializedName("user_id") val userId: String,
    @SerializedName("account_id") val accountId: String,
    val symbol: String,
    val side: String,
    val quantity: Double,
    @SerializedName("remaining_quantity") val remainingQuantity: Double? = null,
    @SerializedName("entry_price") val entryPrice: Double,
    val leverage: Int,
    @SerializedName("margin_type") val marginType: String,
    @SerializedName("entry_order_id") val entryOrderId: Long,
    @SerializedName("tp_order_id") val tpOrderId: Long? = null,
    @SerializedName("sl_order_id") val slOrderId: Long? = null,
    @SerializedName("take_profit_pct") val takeProfitPct: Double? = null,
    @SerializedName("stop_loss_pct") val stopLossPct: Double? = null,
    @SerializedName("tp_price") val tpPrice: Double? = null,
    @SerializedName("sl_price") val slPrice: Double? = null,
    @SerializedName("trailing_stop_enabled") val trailingStopEnabled: Boolean = false,
    @SerializedName("trailing_stop_callback_rate") val trailingStopCallbackRate: Double? = null,
    val status: String,
    @SerializedName("paper_trading") val paperTrading: Boolean = false,
    @SerializedName("exit_price") val exitPrice: Double? = null,
    @SerializedName("exit_order_id") val exitOrderId: Long? = null,
    @SerializedName("exit_reason") val exitReason: String? = null,
    @SerializedName("realized_pnl") val realizedPnl: Double? = null,
    @SerializedName("fee_paid") val feePaid: Double? = null,
    @SerializedName("funding_fee") val fundingFee: Double? = null,
    @SerializedName("current_price") val currentPrice: Double? = null,
    @SerializedName("unrealized_pnl") val unrealizedPnl: Double? = null,
    @SerializedName("liquidation_price") val liquidationPrice: Double? = null,
    @SerializedName("initial_margin") val initialMargin: Double? = null,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String,
    @SerializedName("closed_at") val closedAt: String? = null,
    val notes: String? = null
)

/**
 * List of manual positions
 */
data class ManualPositionListResponseDto(
    val positions: List<ManualPositionResponseDto>,
    val total: Int,
    @SerializedName("open_count") val openCount: Int,
    @SerializedName("closed_count") val closedCount: Int
)
