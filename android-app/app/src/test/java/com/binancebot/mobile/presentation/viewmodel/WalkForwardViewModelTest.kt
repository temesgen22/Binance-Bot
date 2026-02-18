package com.binancebot.mobile.presentation.viewmodel

import app.cash.turbine.test
import com.binancebot.mobile.data.remote.dto.WalkForwardProgressDto
import com.binancebot.mobile.data.remote.dto.WalkForwardResultDto
import com.binancebot.mobile.data.remote.dto.WalkForwardStartResponseDto
import com.binancebot.mobile.domain.repository.WalkForwardRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.yield
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
import org.mockito.kotlin.whenever
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull

@OptIn(ExperimentalCoroutinesApi::class)
class WalkForwardViewModelTest {

    @Mock
    lateinit var walkForwardRepository: WalkForwardRepository

    private lateinit var viewModel: WalkForwardViewModel

    private fun sampleWalkForwardResult() = WalkForwardResultDto(
        symbol = "BTCUSDT",
        strategyType = "scalping",
        overallStartTime = "2024-01-01T00:00:00Z",
        overallEndTime = "2024-01-31T23:59:59Z",
        trainingPeriodDays = 30,
        testPeriodDays = 7,
        stepSizeDays = 7,
        windowType = "rolling",
        totalWindows = 5,
        windows = null,
        totalReturnPct = 8.5,
        avgWindowReturnPct = 1.7,
        consistencyScore = 0.85,
        sharpeRatio = 1.2,
        maxDrawdownPct = 3.0,
        totalTrades = 50,
        avgWinRate = 62.0,
        equityCurve = null
    )

    @Before
    fun setup() = runBlocking {
        MockitoAnnotations.openMocks(this@WalkForwardViewModelTest)
        Dispatchers.setMain(kotlinx.coroutines.test.UnconfinedTestDispatcher())
        whenever(walkForwardRepository.getWalkForwardHistory(any(), any(), anyOrNull(), anyOrNull()))
            .thenReturn(Result.success(emptyList()))
        viewModel = WalkForwardViewModel(walkForwardRepository)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `startWalkForwardAnalysis success sets Running and taskId`() = runTest {
        val startResponse = WalkForwardStartResponseDto("task-123", "Started", 5)
        whenever(walkForwardRepository.startWalkForwardAnalysis(any()))
            .thenReturn(Result.success(startResponse))
        whenever(walkForwardRepository.getWalkForwardProgress("task-123"))
            .thenReturn(Result.success(
                WalkForwardProgressDto("task-123", "running", 1, 5, 20.0, null, "training", null)
            ))

        viewModel.startWalkForwardAnalysis(
            symbol = "BTCUSDT",
            strategyType = "scalping",
            startTime = "2024-01-01",
            endTime = "2024-01-31"
        )
        yield()

        assertEquals(WalkForwardUiState.Running, viewModel.uiState.value)
        assertEquals("task-123", viewModel.currentTaskId.value)
        assertNotNull(viewModel.progress.value)
    }

    @Test
    fun `startWalkForwardAnalysis success when progress completed fetches result and sets Success`() = runTest {
        val startResponse = WalkForwardStartResponseDto("task-456", "Started", 5)
        val resultDto = sampleWalkForwardResult()
        whenever(walkForwardRepository.startWalkForwardAnalysis(any()))
            .thenReturn(Result.success(startResponse))
        whenever(walkForwardRepository.getWalkForwardProgress("task-456"))
            .thenReturn(Result.success(
                WalkForwardProgressDto("task-456", "completed", 5, 5, 100.0, null, null, null)
            ))
        whenever(walkForwardRepository.getWalkForwardResult("task-456"))
            .thenReturn(Result.success(resultDto))

        viewModel.startWalkForwardAnalysis(
            symbol = "BTCUSDT",
            strategyType = "scalping",
            startTime = "2024-01-01",
            endTime = "2024-01-31"
        )
        yield()

        assertEquals(WalkForwardUiState.Success, viewModel.uiState.value)
        assertEquals(resultDto, viewModel.result.value)
        assertEquals(8.5, viewModel.result.value!!.totalReturnPct)
        assertEquals(62.0, viewModel.result.value!!.avgWinRate)
    }

    @Test
    fun `clearCurrentResult resets state to Idle`() = runTest {
        whenever(walkForwardRepository.startWalkForwardAnalysis(any()))
            .thenReturn(Result.success(WalkForwardStartResponseDto("task-1", "Started", 5)))
        whenever(walkForwardRepository.getWalkForwardProgress("task-1"))
            .thenReturn(Result.success(
                WalkForwardProgressDto("task-1", "running", 0, 5, 0.0)
            ))

        viewModel.startWalkForwardAnalysis("BTCUSDT", "scalping", "2024-01-01", "2024-01-31")
        yield()
        assertEquals(WalkForwardUiState.Running, viewModel.uiState.value)

        viewModel.clearCurrentResult()
        assertEquals(WalkForwardUiState.Idle, viewModel.uiState.value)
        assertNull(viewModel.currentTaskId.value)
        assertNull(viewModel.progress.value)
        assertNull(viewModel.result.value)
    }

    @Test
    fun `startWalkForwardAnalysis failure sets Error state`() = runTest {
        whenever(walkForwardRepository.startWalkForwardAnalysis(any()))
            .thenReturn(Result.failure(RuntimeException("Backend unavailable")))

        viewModel.uiState.test {
            skipItems(1) // ignore initial (Idle); StateFlow may conflate Loading
            viewModel.startWalkForwardAnalysis(
                symbol = "BTCUSDT",
                strategyType = "scalping",
                startTime = "2024-01-01",
                endTime = "2024-01-31"
            )
            val error = awaitItem() as WalkForwardUiState.Error
            assertEquals("Backend unavailable", error.message)
            cancelAndIgnoreRemainingEvents()
        }
    }
}
