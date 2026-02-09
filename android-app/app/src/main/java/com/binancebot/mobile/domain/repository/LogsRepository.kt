package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.LogResponse

interface LogsRepository {
    suspend fun getLogs(
        symbol: String? = null,
        level: String? = null,
        dateFrom: String? = null,
        dateTo: String? = null,
        searchText: String? = null,
        limit: Int = 1000,
        offset: Int = 0,
        reverse: Boolean = true
    ): Result<LogResponse>
}



























