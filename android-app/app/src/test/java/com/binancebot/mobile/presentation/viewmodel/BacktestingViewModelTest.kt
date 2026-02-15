package com.binancebot.mobile.presentation.viewmodel

import app.cash.turbine.test
import com.binancebot.mobile.data.remote.dto.BacktestResultDto
import com.binancebot.mobile.domain.repository.BacktestingRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.mockito.Mock
import org.mockito.MockitoAnnotations
import org.mockito.kotlin.any
import org.mockito.kotlin.whenever
import kotlin.test.assertEquals
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class BacktestingViewModelTest {

    @Mock
    lateinit var repository: BacktestingRepository

    private lateinit var viewModel: BacktestingViewModel
    private val testDispatcher = UnconfinedTestDispatcher()

    @Before
    fun setup() {
        MockitoAnnotations.openMocks(this)
        Dispatchers.setMain(testDispatcher)
        viewModel = BacktestingViewModel(repository)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `runBacktest success sets result and adds to history`() = runTest {
        val result = BacktestResultDto(
            symbol = "BTCUSDT",
            strategyType = "scalping",
            startTime = "2024-01-01T00:00:00Z",
            endTime = "2024-01-31T23:59:59Z",
            initialBalance = 1000.0,
            finalBalance = 1050.0,
            totalPnL = 50.0,
            totalReturnPct = 5.0,
            totalTrades = 10,
            completedTrades = 10,
            openTrades = 0,
            winningTrades = 6,
            losingTrades = 4,
            winRate = 60.0,
            totalFees = 1.0,
            avgProfitPerTrade = 5.0,
            largestWin = 20.0,
            largestLoss = -10.0,
            maxDrawdown = 15.0,
            maxDrawdownPct = 1.5,
            trades = null,
            klines = null,
            indicators = null
        )
        whenever(repository.runBacktest(any())).thenReturn(Result.success(result))

        viewModel.uiState.test {
            viewModel.runBacktest("BTCUSDT", "scalping", "2024-01-01", "2024-01-31")
            skipItems(1)
            assertEquals(BacktestingUiState.Loading, awaitItem())
            assertEquals(BacktestingUiState.Success, awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
        assertEquals(result, viewModel.currentBacktestResult.value)
        assertTrue(viewModel.backtestHistory.value.isNotEmpty())
    }

    @Test
    fun `runBacktest failure sets Error state`() = runTest {
        whenever(repository.runBacktest(any())).thenReturn(Result.failure(RuntimeException("Network error")))

        viewModel.uiState.test {
            viewModel.runBacktest("BTCUSDT", "scalping", "2024-01-01", "2024-01-31")
            skipItems(1)
            assertEquals(BacktestingUiState.Loading, awaitItem())
            val error = awaitItem() as BacktestingUiState.Error
            assertEquals("Network error", error.message)
            cancelAndIgnoreRemainingEvents()
        }
    }
}
