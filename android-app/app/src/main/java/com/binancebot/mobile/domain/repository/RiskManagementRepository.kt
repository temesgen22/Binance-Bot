package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.*

/**
 * Repository interface for Risk Management operations.
 */
interface RiskManagementRepository {
    suspend fun getPortfolioRiskStatus(accountId: String? = null): Result<PortfolioRiskStatusDto>
    suspend fun getRiskConfig(accountId: String? = null): Result<RiskManagementConfigDto>
    suspend fun updateRiskConfig(accountId: String? = null, config: RiskManagementConfigDto): Result<RiskManagementConfigDto>
    suspend fun createRiskConfig(accountId: String? = null, config: RiskManagementConfigDto): Result<RiskManagementConfigDto>
    
    // Portfolio Metrics
    suspend fun getPortfolioRiskMetrics(accountId: String? = null): Result<PortfolioRiskMetricsDto>
    
    // Strategy Metrics
    suspend fun getStrategyRiskMetrics(strategyId: String): Result<StrategyRiskMetricsDto>
    suspend fun getAllStrategyRiskMetrics(accountId: String? = null): Result<List<StrategyRiskMetricsDto>>
    
    // Enforcement History
    suspend fun getEnforcementHistory(
        accountId: String? = null,
        eventType: String? = null,
        limit: Int = 50,
        offset: Int = 0
    ): Result<EnforcementHistoryDto>
    
    // Reports
    suspend fun getDailyRiskReport(accountId: String? = null): Result<RiskReportDto>
    suspend fun getWeeklyRiskReport(accountId: String? = null): Result<RiskReportDto>
    
    // Strategy Risk Config
    suspend fun getStrategyRiskConfig(strategyId: String): Result<StrategyRiskConfigDto>
    suspend fun createStrategyRiskConfig(config: StrategyRiskConfigDto): Result<StrategyRiskConfigDto>
    suspend fun updateStrategyRiskConfig(strategyId: String, config: StrategyRiskConfigDto): Result<StrategyRiskConfigDto>
    suspend fun deleteStrategyRiskConfig(strategyId: String): Result<Unit>
}
