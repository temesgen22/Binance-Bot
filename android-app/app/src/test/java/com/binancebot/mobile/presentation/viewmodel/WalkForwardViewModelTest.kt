package com.binancebot.mobile.presentation.viewmodel

import app.cash.turbine.test
import com.binancebot.mobile.domain.repository.WalkForwardRepository
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

@OptIn(ExperimentalCoroutinesApi::class)
class WalkForwardViewModelTest {

    @Mock
    lateinit var walkForwardRepository: WalkForwardRepository

    private lateinit var viewModel: WalkForwardViewModel
    private val testDispatcher = UnconfinedTestDispatcher()

    @Before
    fun setup() = kotlinx.coroutines.runBlocking {
        MockitoAnnotations.openMocks(this@WalkForwardViewModelTest)
        Dispatchers.setMain(testDispatcher)
        whenever(walkForwardRepository.getWalkForwardHistory(any(), any(), any(), any()))
            .thenReturn(Result.success(emptyList()))
        viewModel = WalkForwardViewModel(walkForwardRepository)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `startWalkForwardAnalysis failure sets Error state`() = runTest {
        whenever(walkForwardRepository.startWalkForwardAnalysis(any()))
            .thenReturn(Result.failure(RuntimeException("Backend unavailable")))

        viewModel.uiState.test {
            viewModel.startWalkForwardAnalysis(
                symbol = "BTCUSDT",
                strategyType = "scalping",
                startTime = "2024-01-01",
                endTime = "2024-01-31"
            )
            skipItems(1)
            assertEquals(WalkForwardUiState.Loading, awaitItem())
            val error = awaitItem() as WalkForwardUiState.Error
            assertEquals("Backend unavailable", error.message)
            cancelAndIgnoreRemainingEvents()
        }
    }
}
