package com.binancebot.mobile.presentation.viewmodel

import app.cash.turbine.test
import com.binancebot.mobile.data.remote.dto.TradingReportDto
import com.binancebot.mobile.domain.repository.ReportsRepository
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
class ReportsViewModelTest {

    @Mock
    lateinit var reportsRepository: ReportsRepository

    private lateinit var viewModel: ReportsViewModel
    private val testDispatcher = UnconfinedTestDispatcher()

    @Before
    fun setup() {
        MockitoAnnotations.openMocks(this)
        Dispatchers.setMain(testDispatcher)
        viewModel = ReportsViewModel(reportsRepository)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `loadTradingReport success sets tradingReport and Success state`() = runTest {
        val report = TradingReportDto(
            strategies = emptyList(),
            reportGeneratedAt = "2025-01-15T10:00:00Z"
        )
        whenever(
            reportsRepository.getTradingReport(
                strategyId = any(),
                strategyName = any(),
                symbol = any(),
                startDate = any(),
                endDate = any(),
                accountId = any()
            )
        ).thenReturn(Result.success(report))

        viewModel.uiState.test {
            viewModel.loadTradingReport()
            skipItems(1)
            assertEquals(ReportsUiState.Loading, awaitItem())
            assertEquals(ReportsUiState.Success, awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
        assertNotNull(viewModel.tradingReport.value)
        assertEquals(report, viewModel.tradingReport.value)
    }

    @Test
    fun `loadTradingReport failure sets Error state`() = runTest {
        whenever(
            reportsRepository.getTradingReport(
                strategyId = any(),
                strategyName = any(),
                symbol = any(),
                startDate = any(),
                endDate = any(),
                accountId = any()
            )
        ).thenReturn(Result.failure(RuntimeException("Network error")))

        viewModel.uiState.test {
            viewModel.loadTradingReport()
            skipItems(1)
            assertEquals(ReportsUiState.Loading, awaitItem())
            val error = awaitItem() as ReportsUiState.Error
            assertEquals("Network error", error.message)
            cancelAndIgnoreRemainingEvents()
        }
    }
}
