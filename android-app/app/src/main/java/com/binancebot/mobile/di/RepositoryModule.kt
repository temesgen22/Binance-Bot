package com.binancebot.mobile.di

import com.binancebot.mobile.data.repository.*
import com.binancebot.mobile.domain.repository.*
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * Hilt module for binding repository interfaces to their implementations
 */
@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    
    @Binds
    @Singleton
    abstract fun bindAccountRepository(
        accountRepositoryImpl: AccountRepositoryImpl
    ): AccountRepository
    
    @Binds
    @Singleton
    abstract fun bindAuthRepository(
        authRepositoryImpl: AuthRepositoryImpl
    ): AuthRepository
    
    @Binds
    @Singleton
    abstract fun bindLogsRepository(
        logsRepositoryImpl: LogsRepositoryImpl
    ): LogsRepository
    
    @Binds
    @Singleton
    abstract fun bindMarketAnalyzerRepository(
        marketAnalyzerRepositoryImpl: MarketAnalyzerRepositoryImpl
    ): MarketAnalyzerRepository
    
    @Binds
    @Singleton
    abstract fun bindReportsRepository(
        reportsRepositoryImpl: ReportsRepositoryImpl
    ): ReportsRepository
    
    @Binds
    @Singleton
    abstract fun bindStrategyPerformanceRepository(
        strategyPerformanceRepositoryImpl: StrategyPerformanceRepositoryImpl
    ): StrategyPerformanceRepository
    
    @Binds
    @Singleton
    abstract fun bindTestAccountsRepository(
        testAccountsRepositoryImpl: TestAccountsRepositoryImpl
    ): TestAccountsRepository
    
    @Binds
    @Singleton
    abstract fun bindStrategyRepository(
        strategyRepositoryImpl: StrategyRepositoryImpl
    ): StrategyRepository
    
    @Binds
    @Singleton
    abstract fun bindTradeRepository(
        tradeRepositoryImpl: TradeRepositoryImpl
    ): TradeRepository
    
    @Binds
    @Singleton
    abstract fun bindRiskManagementRepository(
        riskManagementRepositoryImpl: RiskManagementRepositoryImpl
    ): RiskManagementRepository
    
    @Binds
    @Singleton
    abstract fun bindDashboardRepository(
        dashboardRepositoryImpl: DashboardRepositoryImpl
    ): DashboardRepository
    
    @Binds
    @Singleton
    abstract fun bindBacktestingRepository(
        backtestingRepositoryImpl: BacktestingRepositoryImpl
    ): BacktestingRepository
    
    @Binds
    @Singleton
    abstract fun bindWalkForwardRepository(
        walkForwardRepositoryImpl: WalkForwardRepositoryImpl
    ): WalkForwardRepository
    
    @Binds
    @Singleton
    abstract fun bindAutoTuningRepository(
        autoTuningRepositoryImpl: AutoTuningRepositoryImpl
    ): AutoTuningRepository
}
