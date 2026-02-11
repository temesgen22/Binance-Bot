package com.binancebot.mobile.data.remote.api

import com.binancebot.mobile.data.remote.dto.*
import retrofit2.Response
import retrofit2.http.*

/**
 * Main API interface for Binance Bot backend
 * All endpoints match the FastAPI backend routes
 */
interface BinanceBotApi {
    
    // ========== Authentication ==========
    
    @POST("auth/login")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>
    
    @POST("auth/register")
    suspend fun register(@Body request: RegisterRequest): Response<RegisterResponse>
    
    @POST("auth/refresh")
    suspend fun refreshToken(@Body request: RefreshTokenRequest): Response<RefreshTokenResponse>
    
    // Synchronous version for Authenticator (must be synchronous)
    @POST("auth/refresh")
    fun refreshTokenSync(@Body request: RefreshTokenRequest): retrofit2.Call<RefreshTokenResponse>
    
    @GET("auth/me")
    suspend fun getCurrentUser(): Response<UserResponse>
    
    @PUT("auth/profile")
    suspend fun updateProfile(@Body request: UpdateProfileRequest): Response<UserResponse>
    
    @POST("auth/change-password")
    suspend fun changePassword(@Body request: ChangePasswordRequest): Response<Unit>
    
    @POST("auth/logout")
    suspend fun logout(): Response<Unit>
    
    // ========== Logs ==========
    
    @GET("logs")
    suspend fun getLogs(
        @Query("symbol") symbol: String? = null,
        @Query("level") level: String? = null,
        @Query("date_from") dateFrom: String? = null,
        @Query("date_to") dateTo: String? = null,
        @Query("search_text") searchText: String? = null,
        @Query("limit") limit: Int = 100,
        @Query("offset") offset: Int = 0,
        @Query("reverse") reverse: Boolean = false
    ): Response<LogResponse>
    
    // ========== Strategies ==========
    
    @GET("strategies/list")
    suspend fun getStrategies(): Response<List<StrategyDto>>
    
    @GET("strategies/{strategy_id}")
    suspend fun getStrategy(@Path("strategy_id") strategyId: String): Response<StrategyDto>
    
    @POST("strategies/")
    suspend fun createStrategy(@Body request: CreateStrategyRequest): Response<StrategyDto>
    
    @PUT("strategies/{strategy_id}")
    suspend fun updateStrategy(
        @Path("strategy_id") strategyId: String,
        @Body request: UpdateStrategyRequest
    ): Response<StrategyDto>
    
    @DELETE("strategies/{strategy_id}")
    suspend fun deleteStrategy(@Path("strategy_id") strategyId: String): Response<Unit>
    
    @POST("strategies/{strategy_id}/start")
    suspend fun startStrategy(@Path("strategy_id") strategyId: String): Response<Unit>
    
    @POST("strategies/{strategy_id}/stop")
    suspend fun stopStrategy(@Path("strategy_id") strategyId: String): Response<Unit>
    
    @GET("strategies/{strategy_id}/stats")
    suspend fun getStrategyStats(@Path("strategy_id") strategyId: String): Response<StrategyStatsDto>
    
    @GET("strategies/{strategy_id}/health")
    suspend fun getStrategyHealth(@Path("strategy_id") strategyId: String): Response<StrategyHealthDto>
    
    @GET("risk/status/strategy/{strategy_id}")
    suspend fun getStrategyRiskStatus(@Path("strategy_id") strategyId: String): Response<StrategyRiskStatusDto>
    
    @GET("strategies/{strategy_id}/activity")
    suspend fun getStrategyActivity(
        @Path("strategy_id") strategyId: String,
        @Query("limit") limit: Int = 50
    ): Response<List<StrategyActivityDto>>
    
    // ========== Strategy Performance ==========
    
    @GET("strategies/performance")
    suspend fun getStrategyPerformance(
        @Query("strategy_name") strategyName: String? = null,
        @Query("symbol") symbol: String? = null,
        @Query("status") status: String? = null,
        @Query("rank_by") rankBy: String = "total_pnl",
        @Query("start_date") startDate: String? = null,
        @Query("end_date") endDate: String? = null,
        @Query("account_id") accountId: String? = null
    ): Response<StrategyPerformanceListDto>
    
    @GET("strategies/performance/{strategy_id}")
    suspend fun getStrategyPerformanceById(
        @Path("strategy_id") strategyId: String
    ): Response<StrategyPerformanceDto>
    
    // ========== Trading Reports ==========
    
    @GET("reports/trading")
    suspend fun getTradingReport(
        @Query("strategy_id") strategyId: String? = null,
        @Query("strategy_name") strategyName: String? = null,
        @Query("symbol") symbol: String? = null,
        @Query("start_date") startDate: String? = null,
        @Query("end_date") endDate: String? = null,
        @Query("account_id") accountId: String? = null
    ): Response<TradingReportDto>
    
    // ========== Dashboard ==========
    
    @GET("dashboard/overview")
    suspend fun getDashboardOverview(
        @Query("start_date") startDate: String? = null,
        @Query("end_date") endDate: String? = null,
        @Query("account_id") accountId: String? = null
    ): Response<DashboardOverviewDto>
    
    // ========== Market Analyzer ==========
    
    @GET("market-analyzer/analyze")
    suspend fun analyzeMarket(
        @Query("symbol") symbol: String,
        @Query("interval") interval: String = "5m",
        @Query("lookback_period") lookbackPeriod: Int = 150,
        @Query("ema_fast_period") emaFastPeriod: Int = 20,
        @Query("ema_slow_period") emaSlowPeriod: Int = 50,
        @Query("max_ema_spread_pct") maxEmaSpreadPct: Double = 0.005,
        @Query("rsi_period") rsiPeriod: Int = 14,
        @Query("swing_period") swingPeriod: Int = 20
    ): Response<MarketAnalysisResponse>
    
    // ========== Test Accounts ==========
    
    @POST("test-account/test")
    suspend fun testAccount(
        @Body request: TestAccountRequestDto
    ): Response<TestAccountResponseDto>
    
    @POST("test-account/quick-test")
    suspend fun quickTestAccount(
        @Query("api_key") apiKey: String,
        @Query("api_secret") apiSecret: String,
        @Query("testnet") testnet: Boolean
    ): Response<TestAccountResponseDto>
    
    // ========== Trades ==========
    
    @GET("trades/list")
    suspend fun getTrades(
        @Query("strategy_id") strategyId: String? = null,
        @Query("symbol") symbol: String? = null,
        @Query("start_date") startDate: String? = null,
        @Query("end_date") endDate: String? = null,
        @Query("side") side: String? = null,
        @Query("account_id") accountId: String? = null,
        @Query("limit") limit: Int = 100,
        @Query("offset") offset: Int = 0
    ): Response<List<TradeDto>>
    
    @GET("trades/pnl/overview")
    suspend fun getPnLOverview(
        @Query("account_id") accountId: String? = null,
        @Query("start_date") startDate: String? = null,
        @Query("end_date") endDate: String? = null
    ): Response<List<SymbolPnLDto>>
    
    @GET("trades/symbols")
    suspend fun getSymbols(): Response<List<String>>
    
    // ========== Accounts ==========
    
    @GET("accounts/list")
    suspend fun getAccounts(): Response<List<AccountDto>>
    
    @GET("accounts/{account_id}")
    suspend fun getAccount(@Path("account_id") accountId: String): Response<AccountDto>
    
    @POST("accounts/")
    suspend fun createAccount(@Body request: CreateAccountRequest): Response<AccountDto>
    
    // ========== Risk Management ==========
    
    @GET("risk/status/portfolio")
    suspend fun getPortfolioRiskStatus(
        @Query("account_id") accountId: String? = null
    ): Response<PortfolioRiskStatusDto>
    
    @GET("risk/status/realtime")
    suspend fun getRealtimeRiskStatus(
        @Query("account_id") accountId: String? = null
    ): Response<com.binancebot.mobile.data.remote.dto.RealTimeRiskStatusResponseDto>
    
    @GET("risk/config")
    suspend fun getRiskConfig(
        @Query("account_id") accountId: String? = null
    ): Response<RiskManagementConfigDto>
    
    @POST("risk/config")
    suspend fun createRiskConfig(
        @Query("account_id") accountId: String? = null,
        @Body config: RiskManagementConfigDto
    ): Response<RiskManagementConfigDto>
    
    @PUT("risk/config")
    suspend fun updateRiskConfig(
        @Query("account_id") accountId: String? = null,
        @Body config: RiskManagementConfigDto
    ): Response<RiskManagementConfigDto>
    
    @GET("risk/metrics/portfolio")
    suspend fun getPortfolioRiskMetrics(
        @Query("account_id") accountId: String? = null
    ): Response<PortfolioRiskMetricsResponseDto>
    
    @GET("risk/metrics/strategy/{strategy_id}")
    suspend fun getStrategyRiskMetrics(
        @Path("strategy_id") strategyId: String
    ): Response<StrategyRiskMetricsDto>
    
    @GET("risk/enforcement/history")
    suspend fun getEnforcementHistory(
        @Query("account_id") accountId: String? = null,
        @Query("event_type") eventType: String? = null,
        @Query("limit") limit: Int = 50,
        @Query("offset") offset: Int = 0
    ): Response<EnforcementHistoryDto>
    
    @GET("risk/reports/daily")
    suspend fun getDailyRiskReport(
        @Query("account_id") accountId: String? = null
    ): Response<RiskReportResponseDto>
    
    @GET("risk/reports/weekly")
    suspend fun getWeeklyRiskReport(
        @Query("account_id") accountId: String? = null
    ): Response<RiskReportResponseDto>
    
    // Strategy Risk Config
    @GET("risk/config/strategy/{strategy_id}")
    suspend fun getStrategyRiskConfig(
        @Path("strategy_id") strategyId: String
    ): Response<StrategyRiskConfigDto>
    
    @POST("risk/config/strategy/{strategy_id}")
    suspend fun createStrategyRiskConfig(
        @Path("strategy_id") strategyId: String,
        @Body config: StrategyRiskConfigDto
    ): Response<StrategyRiskConfigDto>
    
    @PUT("risk/config/strategy/{strategy_id}")
    suspend fun updateStrategyRiskConfig(
        @Path("strategy_id") strategyId: String,
        @Body config: StrategyRiskConfigDto
    ): Response<StrategyRiskConfigDto>
    
    @DELETE("risk/config/strategy/{strategy_id}")
    suspend fun deleteStrategyRiskConfig(
        @Path("strategy_id") strategyId: String
    ): Response<Unit>
    
    // ========== Backtesting ==========
    
    @POST("backtesting/run")
    suspend fun runBacktest(
        @Body request: BacktestRequestDto
    ): Response<BacktestResultDto>
    
    // ========== Walk-Forward Analysis ==========
    
    @POST("backtesting/walk-forward/start")
    suspend fun startWalkForwardAnalysis(
        @Body request: WalkForwardRequestDto
    ): Response<WalkForwardStartResponseDto>
    
    @GET("backtesting/walk-forward/progress/{task_id}")
    suspend fun getWalkForwardProgress(
        @Path("task_id") taskId: String
    ): Response<WalkForwardProgressDto>
    
    @GET("backtesting/walk-forward/result/{task_id}")
    suspend fun getWalkForwardResult(
        @Path("task_id") taskId: String
    ): Response<WalkForwardResultDto>
    
    @GET("backtesting/walk-forward/history")
    suspend fun getWalkForwardHistory(
        @Query("limit") limit: Int = 50,
        @Query("offset") offset: Int = 0,
        @Query("symbol") symbol: String? = null,
        @Query("strategy_type") strategyType: String? = null
    ): Response<Map<String, Any>> // Returns {"analyses": [...], "total": ...}
    
    // ========== Auto-Tuning ==========
    
    @POST("auto-tuning/strategies/{strategy_id}/enable")
    suspend fun enableAutoTuning(
        @Path("strategy_id") strategyId: String,
        @Body request: EnableAutoTuningRequestDto
    ): Response<Map<String, Any>>
    
    @POST("auto-tuning/strategies/{strategy_id}/disable")
    suspend fun disableAutoTuning(
        @Path("strategy_id") strategyId: String
    ): Response<Map<String, Any>>
    
    @POST("auto-tuning/strategies/{strategy_id}/tune-now")
    suspend fun tuneNow(
        @Path("strategy_id") strategyId: String
    ): Response<Map<String, Any>>
    
    @GET("auto-tuning/strategies/{strategy_id}/status")
    suspend fun getTuningStatus(
        @Path("strategy_id") strategyId: String
    ): Response<TuningStatusResponseDto>
    
    @GET("auto-tuning/strategies/{strategy_id}/history")
    suspend fun getTuningHistory(
        @Path("strategy_id") strategyId: String,
        @Query("limit") limit: Int = 50,
        @Query("offset") offset: Int = 0
    ): Response<Map<String, Any>> // Returns {"history": [...], "total": ...}
    
    // ========== Notifications ==========
    
    @POST("notifications/fcm/register")
    suspend fun registerFcmToken(@Body request: RegisterFcmTokenRequest): Response<RegisterFcmTokenResponse>
    
    @PUT("notifications/preferences")
    suspend fun updateNotificationPreferences(@Body preferences: NotificationPreferencesDto): Response<NotificationPreferencesDto>
    
    @GET("notifications/history")
    suspend fun getNotificationHistory(
        @Query("limit") limit: Int = 50,
        @Query("offset") offset: Int = 0,
        @Query("category") category: String? = null,
        @Query("type") type: String? = null
    ): Response<NotificationHistoryResponseDto>
    
    @PUT("notifications/{notification_id}/read")
    suspend fun markNotificationAsRead(@Path("notification_id") notificationId: String): Response<Unit>
    
    @DELETE("notifications/{notification_id}")
    suspend fun deleteNotification(@Path("notification_id") notificationId: String): Response<Unit>
}
