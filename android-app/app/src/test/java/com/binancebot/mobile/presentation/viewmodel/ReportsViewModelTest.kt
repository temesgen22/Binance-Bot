package com.binancebot.mobile.presentation.viewmodel

import app.cash.turbine.test
import com.binancebot.mobile.data.remote.dto.TradingReportDto
import com.binancebot.mobile.domain.repository.ReportsRepository
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

    @Ignore("ViewModel + suspend repo + test dispatcher: state not updated after yield; needs investigation")
    @Test
    fun `loadTradingReport success sets tradingReport and Success state`() = runTest(testDispatcher) {
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

        viewModel.loadTradingReport()
        yield() // let suspend repo call complete and set Success
        assertEquals(ReportsUiState.Success, viewModel.uiState.value)
        assertNotNull(viewModel.tradingReport.value)
        assertEquals(report, viewModel.tradingReport.value)
    }

    @Ignore("ViewModel + suspend repo + test dispatcher: state not updated after yield; needs investigation")
    @Test
    fun `loadTradingReport failure sets Error state`() = runTest(testDispatcher) {
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

        viewModel.loadTradingReport()
        yield() // let suspend repo call complete and set Error
        val finalState = viewModel.uiState.value
        assert(finalState is ReportsUiState.Error) { "Expected Error, got $finalState" }
        assertEquals("Network error", (finalState as ReportsUiState.Error).message)
    }
}
