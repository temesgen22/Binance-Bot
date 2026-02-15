package com.binancebot.mobile.presentation.viewmodel

import app.cash.turbine.test
import com.binancebot.mobile.data.remote.dto.StrategyPerformanceListDto
import com.binancebot.mobile.domain.repository.StrategyPerformanceRepository
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
import kotlin.test.assertNotNull

@OptIn(ExperimentalCoroutinesApi::class)
class StrategyPerformanceViewModelTest {

    @Mock
    lateinit var repository: StrategyPerformanceRepository

    private lateinit var viewModel: StrategyPerformanceViewModel
    private val testDispatcher = UnconfinedTestDispatcher()

    @Before
    fun setup() = kotlinx.coroutines.runBlocking {
        MockitoAnnotations.openMocks(this@StrategyPerformanceViewModelTest)
        Dispatchers.setMain(testDispatcher)
        whenever(
            repository.getStrategyPerformance(
                strategyName = any(),
                symbol = any(),
                status = any(),
                rankBy = any(),
                startDate = any(),
                endDate = any(),
                accountId = any()
            )
        ).thenReturn(Result.success(StrategyPerformanceListDto()))
        viewModel = StrategyPerformanceViewModel(repository)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `loadPerformance success sets performanceList and Success state`() = runTest {
        val list = StrategyPerformanceListDto(strategies = emptyList(), totalStrategies = 0)
        whenever(
            repository.getStrategyPerformance(
                strategyName = any(),
                symbol = any(),
                status = any(),
                rankBy = any(),
                startDate = any(),
                endDate = any(),
                accountId = any()
            )
        ).thenReturn(Result.success(list))

        viewModel.uiState.test {
            viewModel.loadPerformance()
            skipItems(1)
            assertEquals(StrategyPerformanceUiState.Loading, awaitItem())
            assertEquals(StrategyPerformanceUiState.Success, awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
        assertNotNull(viewModel.performanceList.value)
        assertEquals(list, viewModel.performanceList.value)
    }

    @Test
    fun `loadPerformance failure sets Error state`() = runTest {
        whenever(
            repository.getStrategyPerformance(
                strategyName = any(),
                symbol = any(),
                status = any(),
                rankBy = any(),
                startDate = any(),
                endDate = any(),
                accountId = any()
            )
        ).thenReturn(Result.failure(RuntimeException("Server error")))

        viewModel.uiState.test {
            viewModel.loadPerformance()
            skipItems(1) // skip current (Success from init)
            assertEquals(StrategyPerformanceUiState.Loading, awaitItem())
            val error = awaitItem() as StrategyPerformanceUiState.Error
            assertEquals("Server error", error.message)
            cancelAndIgnoreRemainingEvents()
        }
    }
}
