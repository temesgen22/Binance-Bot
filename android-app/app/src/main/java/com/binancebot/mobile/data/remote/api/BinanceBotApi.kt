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
    
    @GET("risk/config")
    suspend fun getRiskConfig(
        @Query("account_id") accountId: String? = null
    ): Response<RiskManagementConfigDto>
}
