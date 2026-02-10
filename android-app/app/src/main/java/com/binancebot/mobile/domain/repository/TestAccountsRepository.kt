package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.TestAccountRequestDto
import com.binancebot.mobile.data.remote.dto.TestAccountResponseDto

interface TestAccountsRepository {
    suspend fun testAccount(request: TestAccountRequestDto): Result<TestAccountResponseDto>
    suspend fun quickTestAccount(
        apiKey: String,
        apiSecret: String,
        testnet: Boolean = true
    ): Result<TestAccountResponseDto>
}





























