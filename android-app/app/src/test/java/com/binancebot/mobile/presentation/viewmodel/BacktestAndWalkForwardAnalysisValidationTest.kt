package com.binancebot.mobile.presentation.viewmodel

import app.cash.turbine.test
import com.binancebot.mobile.data.remote.dto.BacktestRequestDto
import com.binancebot.mobile.data.remote.dto.BacktestResultDto
import com.binancebot.mobile.data.remote.dto.WalkForwardProgressDto
import com.binancebot.mobile.data.remote.dto.WalkForwardResultDto
import com.binancebot.mobile.data.remote.dto.WalkForwardStartResponseDto
import com.binancebot.mobile.domain.repository.BacktestingRepository
import com.binancebot.mobile.domain.repository.WalkForwardRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.mockito.Mock
import org.mockito.MockitoAnnotations
import org.mockito.kotlin.any
import org.mockito.kotlin.anyOrNull
import org.mockito.kotlin.argumentCaptor
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * Validation tests for Backtesting and Walk-Forward Analysis flows.
 * Ensures run backtest, start walk-forward, result handling, and state transitions behave correctly.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class BacktestAndWalkForwardAnalysisValidationTest {

    @Mock
    lateinit var backtestingRepository: BacktestingRepository

    @Mock
    lateinit var walkForwardRepository: WalkForwardRepository

    private lateinit var backtestingViewModel: BacktestingViewModel
    private lateinit var walkForwardViewModel: WalkForwardViewModel
    private val testDispatcher = StandardTestDispatcher()

    @Before
    fun setup() = runBlocking {
        MockitoAnnotations.openMocks(this@BacktestAndWalkForwardAnalysisValidationTest)
        Dispatchers.setMain(testDispatcher)
        backtestingViewModel = BacktestingViewModel(backtestingRepository)
        whenever(walkForwardRepository.getWalkForwardHistory(any(), any(), anyOrNull(), anyOrNull()))
            .thenReturn(Result.success(emptyList()))
        walkForwardViewModel = WalkForwardViewModel(walkForwardRepository)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    // ---------- Backtesting validation ----------

    @Test
    fun `backtesting run sends correct request and updates result and history`() = runTest {
        val result = BacktestResultDto(
            symbol = "BTCUSDT",
            strategyType = "scalping",
            startTime = "2024-01-01T00:00:00Z",
            endTime = "2024-01-31T23:59:59Z",
            initialBalance = 1000.0,
            finalBalance = 1100.0,
            totalPnL = 100.0,
            totalReturnPct = 10.0,
            totalTrades = 20,
            completedTrades = 20,
            openTrades = 0,
            winningTrades = 12,
            losingTrades = 8,
            winRate = 60.0,
            totalFees = 2.0,
            avgProfitPerTrade = 5.0,
            largestWin = 25.0,
            largestLoss = -15.0,
            maxDrawdown = 20.0,
            maxDrawdownPct = 2.0,
            trades = null,
            klines = null,
            indicators = null
        )
        whenever(backtestingRepository.runBacktest(any())).thenReturn(Result.success(result))

        backtestingViewModel.runBacktest(
            symbol = "BTCUSDT",
            strategyType = "scalping",
            startTime = "2024-01-01",
            endTime = "2024-01-31",
            leverage = 10,
            initialBalance = 1000.0
        )

        backtestingViewModel.uiState.test {
            skipItems(1)
            assertEquals(BacktestingUiState.Success, awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
        assertNotNull(backtestingViewModel.currentBacktestResult.value)
        assertEquals(10.0, backtestingViewModel.currentBacktestResult.value!!.totalReturnPct)
        assertEquals(60.0, backtestingViewModel.currentBacktestResult.value!!.winRate)
        assertTrue(backtestingViewModel.backtestHistory.value.isNotEmpty())

        val captor = argumentCaptor<BacktestRequestDto>()
        verify(backtestingRepository).runBacktest(captor.capture())
        val request = captor.firstValue
        assertEquals("BTCUSDT", request.symbol)
        assertEquals("scalping", request.strategyType)
        assertEquals(10, request.leverage)
        assertTrue(request.startTime.contains("2024-01-01"))
        assertTrue(request.endTime.contains("2024-01-31"))
    }

    @Test
    fun `walk-forward start runs to completion and sets result with metrics`() = runTest {
        whenever(walkForwardRepository.startWalkForwardAnalysis(any()))
            .thenReturn(Result.success(WalkForwardStartResponseDto("wf-task-1", "Started", 5)))
        whenever(walkForwardRepository.getWalkForwardProgress("wf-task-1"))
            .thenReturn(Result.success(
                WalkForwardProgressDto("wf-task-1", "completed", 5, 5, 100.0, null, null, null)
            ))
        val wfResult = WalkForwardResultDto(
            symbol = "ETHUSDT",
            strategyType = "range_mean_reversion",
            overallStartTime = "2024-01-01T00:00:00Z",
            overallEndTime = "2024-03-31T23:59:59Z",
            trainingPeriodDays = 30,
            testPeriodDays = 7,
            stepSizeDays = 7,
            windowType = "rolling",
            totalWindows = 10,
            windows = null,
            totalReturnPct = 15.0,
            avgWindowReturnPct = 1.5,
            consistencyScore = 0.9,
            sharpeRatio = 1.5,
            maxDrawdownPct = 2.5,
            totalTrades = 100,
            avgWinRate = 58.0,
            equityCurve = null
        )
        whenever(walkForwardRepository.getWalkForwardResult("wf-task-1"))
            .thenReturn(Result.success(wfResult))

        walkForwardViewModel.startWalkForwardAnalysis(
            symbol = "ETHUSDT",
            strategyType = "range_mean_reversion",
            startTime = "2024-01-01",
            endTime = "2024-03-31",
            trainingPeriodDays = 30,
            testPeriodDays = 7,
            stepSizeDays = 7
        )
        testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(WalkForwardUiState.Success, walkForwardViewModel.uiState.value)
        assertNotNull(walkForwardViewModel.result.value)
        assertEquals(15.0, walkForwardViewModel.result.value!!.totalReturnPct)
        assertEquals(58.0, walkForwardViewModel.result.value!!.avgWinRate)
        assertEquals("ETHUSDT", walkForwardViewModel.result.value!!.symbol)
    }
}
