package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.domain.model.Account

/**
 * Repository interface for Account operations.
 */
interface AccountRepository {
    suspend fun getAccounts(): Result<List<Account>>
    suspend fun getAccount(accountId: String): Result<Account>
    suspend fun createAccount(request: com.binancebot.mobile.data.remote.dto.CreateAccountRequest): Result<Account>
}






























