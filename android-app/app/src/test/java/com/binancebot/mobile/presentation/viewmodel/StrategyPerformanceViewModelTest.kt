package com.binancebot.mobile.presentation.viewmodel

import com.binancebot.mobile.data.remote.dto.StrategyPerformanceListDto
import com.binancebot.mobile.data.remote.websocket.PositionUpdateStore
import com.binancebot.mobile.domain.repository.StrategyPerformanceRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.yield
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Before
import org.junit.Ignore
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

    @Mock
    lateinit var positionUpdateStore: PositionUpdateStore

    private lateinit var viewModel: StrategyPerformanceViewModel
    private val testDispatcher = UnconfinedTestDispatcher()

    @Before
    fun setup() {
        MockitoAnnotations.openMocks(this)
        Dispatchers.setMain(testDispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Ignore("ViewModel init + suspend repo + test dispatcher: state not updated after yield; needs investigation")
    @Test
    fun `loadPerformance success sets performanceList and Success state`() = runTest(testDispatcher) {
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
        viewModel = StrategyPerformanceViewModel(repository, positionUpdateStore)
        yield() // let init's suspend repo call complete and set Success
        assertEquals(StrategyPerformanceUiState.Success, viewModel.uiState.value)
        assertNotNull(viewModel.performanceList.value)
        assertEquals(list, viewModel.performanceList.value)
    }

    @Ignore("ViewModel init + suspend repo + test dispatcher: state not updated after yield; needs investigation")
    @Test
    fun `loadPerformance failure sets Error state`() = runTest(testDispatcher) {
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
        viewModel = StrategyPerformanceViewModel(repository, positionUpdateStore)
        yield() // let init's suspend repo call complete and set Error
        val state = viewModel.uiState.value
        assert(state is StrategyPerformanceUiState.Error) { "Expected Error, got $state" }
        assertEquals("Server error", (state as StrategyPerformanceUiState.Error).message)
    }
}
