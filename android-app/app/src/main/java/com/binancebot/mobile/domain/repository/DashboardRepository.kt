package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.DashboardOverviewDto

interface DashboardRepository {
    suspend fun getDashboardOverview(
        startDate: String? = null,
        endDate: String? = null,
        accountId: String? = null
    ): Result<DashboardOverviewDto>
}
