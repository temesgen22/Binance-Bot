package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.PortfolioRiskStatusDto
import com.binancebot.mobile.data.remote.dto.RiskManagementConfigDto

/**
 * Repository interface for Risk Management operations.
 */
interface RiskManagementRepository {
    suspend fun getPortfolioRiskStatus(accountId: String? = null): Result<PortfolioRiskStatusDto>
    suspend fun getRiskConfig(accountId: String? = null): Result<RiskManagementConfigDto>
}
