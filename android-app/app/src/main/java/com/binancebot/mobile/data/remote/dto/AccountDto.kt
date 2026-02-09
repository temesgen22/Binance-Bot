package com.binancebot.mobile.data.remote.dto

import com.google.gson.annotations.SerializedName

/**
 * DTO for Account response from API
 */
data class AccountDto(
    @SerializedName("account_id")
    val accountId: String,
    @SerializedName("name")
    val name: String? = null,
    @SerializedName("exchange_platform")
    val exchangePlatform: String = "binance",
    @SerializedName("testnet")
    val testnet: Boolean = true,
    @SerializedName("is_default")
    val isDefault: Boolean = false,
    @SerializedName("is_active")
    val isActive: Boolean = true,
    @SerializedName("paper_trading")
    val paperTrading: Boolean = false,
    @SerializedName("paper_balance")
    val paperBalance: Double? = null,
    @SerializedName("created_at")
    val createdAt: String? = null
) {
    fun toDomain(): com.binancebot.mobile.domain.model.Account {
        return com.binancebot.mobile.domain.model.Account(
            id = null,  // API doesn't return database UUID
            accountId = accountId,
            name = name,
            exchangePlatform = exchangePlatform,
            testnet = testnet,
            isDefault = isDefault,
            isActive = isActive,
            paperTrading = paperTrading,
            paperBalance = paperBalance,
            createdAt = createdAt
        )
    }
}
