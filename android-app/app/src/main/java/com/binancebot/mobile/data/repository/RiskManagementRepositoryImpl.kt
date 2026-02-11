package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.*
import com.binancebot.mobile.domain.repository.RiskManagementRepository
import com.binancebot.mobile.domain.repository.StrategyRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class RiskManagementRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi,
    private val strategyRepository: com.binancebot.mobile.domain.repository.StrategyRepository
) : RiskManagementRepository {
    
    override suspend fun getPortfolioRiskStatus(accountId: String?): Result<PortfolioRiskStatusDto> {
        return retryApiCall {
            // Use realtime endpoint (same as web app) which calculates actual risk status
            val response = api.getRealtimeRiskStatus(accountId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> {
                    val realtimeData = it.data
                    // Map RealTimeRiskStatusResponseDto to PortfolioRiskStatusDto
                    val currentExposure = realtimeData.currentExposure
                    val lossLimits = realtimeData.lossLimits
                    val drawdown = realtimeData.drawdown
                    val circuitBreakers = realtimeData.circuitBreakers
                    
                    // Extract circuit breaker names from the circuit_breakers object
                    val activeCircuitBreakersList = mutableListOf<String>()
                    if (circuitBreakers != null) {
                        val breakers = circuitBreakers["breakers"] as? List<*>
                        if (breakers != null) {
                            breakers.forEach { breaker ->
                                if (breaker is Map<*, *>) {
                                    val breakerName = breaker["name"] as? String
                                    if (breakerName != null) {
                                        activeCircuitBreakersList.add(breakerName)
                                    }
                                } else if (breaker is String) {
                                    activeCircuitBreakersList.add(breaker)
                                }
                            }
                        }
                    }
                    
                    // Extract warnings from recent enforcement events
                    val warningsList = mutableListOf<String>()
                    realtimeData.recentEnforcementEvents?.forEach { event ->
                        val message = event["message"] as? String
                        if (message != null && !message.isBlank()) {
                            warningsList.add(message)
                        }
                    }
                    
                    // Map the nested structure to flat PortfolioRiskStatusDto
                    val portfolioStatus = PortfolioRiskStatusDto(
                        status = realtimeData.riskStatus, // This is the actual calculated status (normal/warning/breach/paused)
                        totalExposure = (currentExposure?.get("total_exposure_usdt") as? Number)?.toDouble(),
                        totalExposurePct = (currentExposure?.get("total_exposure_pct") as? Number)?.toDouble(),
                        dailyPnL = (lossLimits?.get("daily_loss_usdt") as? Number)?.toDouble(),
                        dailyPnLPct = (lossLimits?.get("daily_loss_pct") as? Number)?.toDouble(),
                        weeklyPnL = (lossLimits?.get("weekly_loss_usdt") as? Number)?.toDouble(),
                        weeklyPnLPct = (lossLimits?.get("weekly_loss_pct") as? Number)?.toDouble(),
                        currentDrawdownPct = (drawdown?.get("current_drawdown_pct") as? Number)?.toDouble(),
                        maxDrawdownPct = (drawdown?.get("max_drawdown_pct") as? Number)?.toDouble(),
                        maxDrawdownLimitPct = (drawdown?.get("max_drawdown_pct") as? Number)?.toDouble(), // Use max_drawdown_pct as limit
                        accountId = realtimeData.accountId,
                        activeCircuitBreakers = if (activeCircuitBreakersList.isNotEmpty()) activeCircuitBreakersList else null,
                        warnings = if (warningsList.isNotEmpty()) warningsList else null
                    )
                    Result.success(portfolioStatus)
                }
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getRiskConfig(accountId: String?): Result<RiskManagementConfigDto> {
        return retryApiCall {
            val response = api.getRiskConfig(accountId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun updateRiskConfig(accountId: String?, config: RiskManagementConfigDto): Result<RiskManagementConfigDto> {
        return retryApiCall {
            val response = api.updateRiskConfig(accountId, config)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun createRiskConfig(accountId: String?, config: RiskManagementConfigDto): Result<RiskManagementConfigDto> {
        return retryApiCall {
            val response = api.createRiskConfig(accountId, config)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getPortfolioRiskMetrics(accountId: String?): Result<com.binancebot.mobile.data.remote.dto.PortfolioRiskMetricsDto> {
        return retryApiCall {
            val response = api.getPortfolioRiskMetrics(accountId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> {
                    // Extract nested metrics and merge with account_id
                    val responseDto = it.data as? com.binancebot.mobile.data.remote.dto.PortfolioRiskMetricsResponseDto
                    val metrics = responseDto?.metrics
                    if (metrics != null) {
                        // Merge account_id from response into metrics
                        val mergedMetrics = metrics.copy(
                            accountId = responseDto.accountId ?: metrics.accountId,
                            timestamp = responseDto.calculatedAt ?: metrics.timestamp
                        )
                        Result.success(mergedMetrics)
                    } else {
                        Result.failure(Exception("No metrics data in response"))
                    }
                }
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getStrategyRiskMetrics(strategyId: String): Result<StrategyRiskMetricsDto> {
        return retryApiCall {
            val response = api.getStrategyRiskMetrics(strategyId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getAllStrategyRiskMetrics(accountId: String?): Result<List<StrategyRiskMetricsDto>> {
        return try {
            // Fetch all strategies
            val strategiesResult = strategyRepository.getStrategies()
            val strategies = strategiesResult.getOrElse { return Result.failure(it) }
            
            // Filter by account if specified
            val filteredStrategies = if (accountId != null) {
                strategies.filter { it.accountId == accountId }
            } else {
                strategies
            }
            
            // Fetch risk metrics for each strategy
            val metricsList = mutableListOf<StrategyRiskMetricsDto>()
            filteredStrategies.forEach { strategy ->
                try {
                    val metricsResult = getStrategyRiskMetrics(strategy.id)
                    metricsResult.onSuccess { metrics ->
                        // Ensure strategy name is populated from the strategy list
                        val metricsWithName = metrics.copy(
                            strategyName = metrics.strategyName?.takeIf { it.isNotBlank() } ?: strategy.name,
                            symbol = metrics.symbol ?: strategy.symbol
                        )
                        metricsList.add(metricsWithName)
                    }.onFailure { 
                        // Add strategy with error message
                        metricsList.add(
                            StrategyRiskMetricsDto(
                                strategyId = strategy.id,
                                strategyName = strategy.name,
                                symbol = strategy.symbol,
                                metrics = null,
                                message = "Failed to load metrics: ${it.message}"
                            )
                        )
                    }
                } catch (e: Exception) {
                    // Add strategy with error message
                    metricsList.add(
                        StrategyRiskMetricsDto(
                            strategyId = strategy.id,
                            strategyName = strategy.name,
                            symbol = strategy.symbol,
                            metrics = null,
                            message = "Error loading metrics: ${e.message}"
                        )
                    )
                }
            }
            
            Result.success(metricsList)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    override suspend fun getEnforcementHistory(
        accountId: String?,
        eventType: String?,
        limit: Int,
        offset: Int
    ): Result<EnforcementHistoryDto> {
        return retryApiCall {
            val response = api.getEnforcementHistory(accountId, eventType, limit, offset)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getDailyRiskReport(accountId: String?): Result<RiskReportDto> {
        return retryApiCall {
            val response = api.getDailyRiskReport(accountId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> {
                    val responseDto = it.data
                    val summary = responseDto.summary
                    // Flatten the nested structure
                    val reportDto = RiskReportDto(
                        date = responseDto.date,
                        weekStart = null,
                        weekEnd = null,
                        totalTrades = summary?.totalTrades,
                        winRate = summary?.winRate,
                        totalPnL = summary?.totalPnL,
                        profitFactor = summary?.profitFactor,
                        maxDrawdownPct = summary?.maxDrawdownPct,
                        sharpeRatio = summary?.sharpeRatio,
                        dailyLoss = summary?.grossLoss?.let { if (it < 0) it else null },
                        weeklyLoss = null
                    )
                    Result.success(reportDto)
                }
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getWeeklyRiskReport(accountId: String?): Result<RiskReportDto> {
        return retryApiCall {
            val response = api.getWeeklyRiskReport(accountId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> {
                    val responseDto = it.data
                    val summary = responseDto.summary
                    // Flatten the nested structure
                    val reportDto = RiskReportDto(
                        date = null,
                        weekStart = responseDto.weekStart,
                        weekEnd = responseDto.weekEnd,
                        totalTrades = summary?.totalTrades,
                        winRate = summary?.winRate,
                        totalPnL = summary?.totalPnL,
                        profitFactor = summary?.profitFactor,
                        maxDrawdownPct = summary?.maxDrawdownPct,
                        sharpeRatio = summary?.sharpeRatio,
                        dailyLoss = null,
                        weeklyLoss = summary?.grossLoss?.let { if (it < 0) it else null }
                    )
                    Result.success(reportDto)
                }
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getStrategyRiskConfig(strategyId: String): Result<StrategyRiskConfigDto> {
        return retryApiCall {
            val response = api.getStrategyRiskConfig(strategyId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun createStrategyRiskConfig(config: StrategyRiskConfigDto): Result<StrategyRiskConfigDto> {
        return retryApiCall {
            val response = api.createStrategyRiskConfig(config.strategyId, config)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun updateStrategyRiskConfig(strategyId: String, config: StrategyRiskConfigDto): Result<StrategyRiskConfigDto> {
        return retryApiCall {
            val response = api.updateStrategyRiskConfig(strategyId, config)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun deleteStrategyRiskConfig(strategyId: String): Result<Unit> {
        return retryApiCall {
            val response = api.deleteStrategyRiskConfig(strategyId)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(Unit)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
}
