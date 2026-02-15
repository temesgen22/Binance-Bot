package com.binancebot.mobile.presentation.util

import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class FormatUtilsTest {

    @Test
    fun formatPrice_removesTrailingZeros() {
        assertEquals("0.0045", FormatUtils.formatPrice(0.0045))
        assertEquals("97234.5", FormatUtils.formatPrice(97234.5))
        assertEquals("1", FormatUtils.formatPrice(1.0))
    }

    @Test
    fun formatPrice_upToEightDecimals() {
        assertEquals("0.12345678", FormatUtils.formatPrice(0.12345678))
    }

    @Test
    fun formatPercentage_multipliesBy100() {
        val result = FormatUtils.formatPercentage(0.5)
        assertTrue(result.contains("50"), "Expected result to contain '50', got: $result")
        assertTrue(result.contains("%"), "Expected result to contain '%', got: $result")
    }

    @Test
    fun formatDateTime_validIso_returnsFormatted() {
        val result = FormatUtils.formatDateTime("2025-01-15T10:30:00Z")
        assertTrue(result.contains("2025"), "Expected result to contain '2025', got: $result")
        assertTrue(result.contains("10") || result.contains("30"), "Expected time part, got: $result")
    }

    @Test
    fun formatDateTime_nullOrBlank_returnsNA() {
        assertEquals("N/A", FormatUtils.formatDateTime(null))
        assertEquals("N/A", FormatUtils.formatDateTime(""))
    }

    @Test
    fun formatDateTime_invalidString_returnsInvalidDate() {
        val result = FormatUtils.formatDateTime("not-a-date")
        assertTrue(result == "Invalid Date" || result.contains("Invalid"), "Expected Invalid Date, got: $result")
    }
}
