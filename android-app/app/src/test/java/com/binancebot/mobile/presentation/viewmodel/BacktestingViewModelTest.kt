package com.binancebot.mobile.presentation.viewmodel

import app.cash.turbine.test
import com.binancebot.mobile.data.remote.dto.BacktestRequestDto
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
import org.mockito.kotlin.argumentCaptor
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class BacktestingViewModelTest {

    @Mock
    lateinit var repository: BacktestingRepository

    private lateinit var viewModel: BacktestingViewModel
    private val testDispatcher = UnconfinedTestDispatcher()

    private fun sampleBacktestResult(
        symbol: String = "BTCUSDT",
        totalReturnPct: Double = 5.0,
        winRate: Double = 60.0
    ) = BacktestResultDto(
        symbol = symbol,
        strategyType = "scalping",
        startTime = "2024-01-01T00:00:00Z",
        endTime = "2024-01-31T23:59:59Z",
        initialBalance = 1000.0,
        finalBalance = 1050.0,
        totalPnL = 50.0,
        totalReturnPct = totalReturnPct,
        totalTrades = 10,
        completedTrades = 10,
        openTrades = 0,
        winningTrades = 6,
        losingTrades = 4,
        winRate = winRate,
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
        val result = sampleBacktestResult()
        whenever(repository.runBacktest(any())).thenReturn(Result.success(result))

        viewModel.uiState.test {
            skipItems(1) // ignore initial (Idle); StateFlow may conflate Loading
            viewModel.runBacktest("BTCUSDT", "scalping", "2024-01-01", "2024-01-31")
            assertEquals(BacktestingUiState.Success, awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
        assertEquals(result, viewModel.currentBacktestResult.value)
        assertTrue(viewModel.backtestHistory.value.isNotEmpty())
    }

    @Test
    fun `runBacktest success validates result metrics`() = runTest {
        val result = sampleBacktestResult(totalReturnPct = 12.5, winRate = 65.0)
        whenever(repository.runBacktest(any())).thenReturn(Result.success(result))

        viewModel.runBacktest("BTCUSDT", "scalping", "2024-01-01", "2024-01-31")

        viewModel.uiState.test {
            skipItems(1)
            assertEquals(BacktestingUiState.Success, awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
        val current = viewModel.currentBacktestResult.value
        assertNotNull(current)
        assertEquals(12.5, current!!.totalReturnPct)
        assertEquals(65.0, current.winRate)
        assertEquals("BTCUSDT", current.symbol)
        assertEquals("scalping", current.strategyType)
    }

    @Test
    fun `runBacktest converts YYYY-MM-DD dates to ISO 8601 in request`() = runTest {
        val result = sampleBacktestResult()
        whenever(repository.runBacktest(any())).thenReturn(Result.success(result))

        viewModel.runBacktest("BTCUSDT", "scalping", "2024-01-01", "2024-06-15")

        val captor = argumentCaptor<BacktestRequestDto>()
        verify(repository).runBacktest(captor.capture())
        val request = captor.firstValue
        assertTrue(request.startTime.contains("2024-01-01"), "startTime should be ISO with 2024-01-01: ${request.startTime}")
        assertTrue(request.endTime.contains("2024-06-15"), "endTime should be ISO with 2024-06-15: ${request.endTime}")
        assertEquals("BTCUSDT", request.symbol)
        assertEquals("scalping", request.strategyType)
    }

    @Test
    fun `runBacktest success prepends result to history newest first`() = runTest {
        val first = sampleBacktestResult(symbol = "BTCUSDT", totalReturnPct = 5.0)
        val second = sampleBacktestResult(symbol = "ETHUSDT", totalReturnPct = 8.0)
        whenever(repository.runBacktest(any()))
            .thenReturn(Result.success(first))
            .thenReturn(Result.success(second))

        viewModel.runBacktest("BTCUSDT", "scalping", "2024-01-01", "2024-01-31")
        viewModel.uiState.test { skipItems(1); awaitItem(); cancelAndIgnoreRemainingEvents() }

        viewModel.runBacktest("ETHUSDT", "scalping", "2024-02-01", "2024-02-28")
        viewModel.uiState.test { skipItems(1); awaitItem(); cancelAndIgnoreRemainingEvents() }

        val history = viewModel.backtestHistory.value
        assertEquals(2, history.size)
        assertEquals("ETHUSDT", history[0].symbol)
        assertEquals("BTCUSDT", history[1].symbol)
    }

    @Test
    fun `clearCurrentResult clears current result`() = runTest {
        val result = sampleBacktestResult()
        whenever(repository.runBacktest(any())).thenReturn(Result.success(result))
        viewModel.runBacktest("BTCUSDT", "scalping", "2024-01-01", "2024-01-31")
        viewModel.uiState.test { skipItems(1); awaitItem(); cancelAndIgnoreRemainingEvents() }
        assertNotNull(viewModel.currentBacktestResult.value)

        viewModel.clearCurrentResult()
        assertEquals(null, viewModel.currentBacktestResult.value)
    }

    @Test
    fun `runBacktest failure sets Error state`() = runTest {
        whenever(repository.runBacktest(any())).thenReturn(Result.failure(RuntimeException("Network error")))

        viewModel.uiState.test {
            skipItems(1) // ignore initial (Idle); StateFlow may conflate Loading
            viewModel.runBacktest("BTCUSDT", "scalping", "2024-01-01", "2024-01-31")
            val error = awaitItem() as BacktestingUiState.Error
            assertEquals("Network error", error.message)
            cancelAndIgnoreRemainingEvents()
        }
    }
}
