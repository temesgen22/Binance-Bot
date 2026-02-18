package com.binancebot.mobile.presentation.util

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/**
 * Shared date/filter utilities for screens that use date ranges (Strategies, Reports, Dashboard, Backtesting).
 * Use a single format and helper so parsing and API params are consistent.
 */
object DateFilterHelper {
    /** Date format used for API query params (e.g. startDate, endDate). */
    const val API_DATE_FORMAT = "yyyy-MM-dd"

    private val apiFormat = SimpleDateFormat(API_DATE_FORMAT, Locale.US)

    /**
     * Returns (startDate, endDate) as strings for the last N days from today.
     * Use for default filter range when no dates are selected.
     */
    fun defaultRangeLastDays(days: Int = 30): Pair<String, String> {
        val cal = Calendar.getInstance()
        val end = apiFormat.format(cal.time)
        cal.add(Calendar.DAY_OF_MONTH, -days)
        val start = apiFormat.format(cal.time)
        return start to end
    }

    /** Format a [Date] for API params. */
    fun formatForApi(date: Date): String = apiFormat.format(date)

    /** Parse a string in [API_DATE_FORMAT] to [Date]; returns null if invalid. */
    fun parseFromApi(value: String?): Date? {
        if (value.isNullOrBlank()) return null
        return try {
            apiFormat.parse(value)
        } catch (_: Exception) {
            null
        }
    }
}
