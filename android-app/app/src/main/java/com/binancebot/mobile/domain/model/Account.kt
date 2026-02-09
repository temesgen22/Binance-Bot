package com.binancebot.mobile.domain.model

/**
 * Domain model for Account
 */
data class Account(
    val id: String? = null,  // Database UUID (nullable as it may not always be present)
    val accountId: String,  // User's local account identifier (Binance account ID)
    val name: String? = null,
    val exchangePlatform: String = "binance",
    val testnet: Boolean = true,
    val isDefault: Boolean = false,
    val isActive: Boolean = true,
    val paperTrading: Boolean = false,
    val paperBalance: Double? = null,
    val createdAt: String? = null
)
