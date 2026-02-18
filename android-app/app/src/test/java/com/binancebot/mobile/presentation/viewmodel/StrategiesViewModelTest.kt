package com.binancebot.mobile.presentation.viewmodel

import app.cash.turbine.test
import com.binancebot.mobile.data.remote.dto.StrategyHealthDto
import com.binancebot.mobile.domain.model.Strategy
import com.binancebot.mobile.domain.repository.StrategyRepository
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
import org.mockito.kotlin.whenever
import kotlin.test.assertEquals
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class StrategiesViewModelTest {

    @Mock
    lateinit var strategyRepository: StrategyRepository

    private lateinit var viewModel: StrategiesViewModel
    private val testDispatcher = UnconfinedTestDispatcher()

    @Before
    fun setup() = kotlinx.coroutines.runBlocking {
        MockitoAnnotations.openMocks(this@StrategiesViewModelTest)
        Dispatchers.setMain(testDispatcher)
        whenever(strategyRepository.getStrategies()).thenReturn(Result.success(emptyList<Strategy>()))
        viewModel = StrategiesViewModel(strategyRepository)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `loadStrategyHealth success adds health to strategyHealth map`() = runTest {
        val strategyId = "strat-1"
        val health = StrategyHealthDto(
            strategyId = strategyId,
            healthStatus = "healthy"
        )
        whenever(strategyRepository.getStrategyHealth(strategyId)).thenReturn(Result.success(health))

        viewModel.strategyHealth.test {
            skipItems(1) // initial empty map
            viewModel.loadStrategyHealth(strategyId)
            val map = awaitItem()
            assertTrue(map.containsKey(strategyId))
            assertEquals("healthy", map[strategyId]?.healthStatus)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `loadStrategyHealth failure does not add to map`() = runTest {
        whenever(strategyRepository.getStrategyHealth("strat-fail"))
            .thenReturn(Result.failure(RuntimeException("Network error")))

        viewModel.strategyHealth.test {
            skipItems(1) // initial
            viewModel.loadStrategyHealth("strat-fail")
            val map = awaitItem()
            assertTrue(!map.containsKey("strat-fail"))
            cancelAndIgnoreRemainingEvents()
        }
    }
}
