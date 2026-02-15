package com.binancebot.mobile.presentation.util

import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class BacktestStrategyDefaultsTest {

    @Test
    fun STRATEGY_TYPES_containsExpectedTypes() {
        val types = BacktestStrategyDefaults.STRATEGY_TYPES.map { it.first }
        assertTrue(types.contains("scalping"))
        assertTrue(types.contains("reverse_scalping"))
        assertTrue(types.contains("range_mean_reversion"))
        assertEquals(3, types.size)
    }

    @Test
    fun getDefaultParams_scalping_hasKlineInterval() {
        val params = BacktestStrategyDefaults.getDefaultParams("scalping")
        assertEquals("1m", params["kline_interval"])
    }

    @Test
    fun getDefaultParams_rangeMeanReversion_hasLookback() {
        val params = BacktestStrategyDefaults.getDefaultParams("range_mean_reversion")
        assertEquals(150, params["lookback_period"])
    }

    @Test
    fun getDefaultParams_unknown_returnsEmpty() {
        assertTrue(BacktestStrategyDefaults.getDefaultParams("unknown").isEmpty())
    }
}
