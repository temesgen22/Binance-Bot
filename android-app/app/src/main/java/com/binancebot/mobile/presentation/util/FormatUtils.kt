package com.binancebot.mobile.presentation.util

import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.*

object FormatUtils {
    private val currencyFormatter = NumberFormat.getCurrencyInstance(Locale.getDefault()).apply {
        maximumFractionDigits = 2
    }
    
    private val dateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
        .withZone(ZoneId.systemDefault())
    
    fun formatCurrency(amount: Double): String {
        return currencyFormatter.format(amount)
    }
    
    fun formatPercentage(value: Double, decimals: Int = 2): String {
        return String.format(Locale.getDefault(), "%.${decimals}f%%", value * 100)
    }
    
    fun formatNumber(value: Double, decimals: Int = 2): String {
        return String.format(Locale.getDefault(), "%.${decimals}f", value)
    }

    /**
     * Format price with full precision (up to 8 decimals), trailing zeros removed.
     * Matches Binance-style display so prices are not cut.
     */
    fun formatPrice(price: Double): String {
        val s = String.format(Locale.US, "%.8f", price)
        return s.trimEnd('0').trimEnd('.')
    }
    
    /**
     * Format ISO date string to readable format
     * @param dateString ISO 8601 date string (e.g., "2025-01-15T10:30:00Z")
     * @return Formatted date string or "N/A" if invalid
     */
    fun formatDateTime(dateString: String?): String {
        if (dateString.isNullOrBlank()) return "N/A"
        return try {
            val instant = Instant.parse(dateString)
            dateTimeFormatter.format(instant)
        } catch (e: Exception) {
            // Fallback to SimpleDateFormat for older formats
            try {
                val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.getDefault())
                val date = sdf.parse(dateString)
                if (date != null) {
                    SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(date)
                } else {
                    "Invalid Date"
                }
            } catch (e2: Exception) {
                "Invalid Date"
            }
        }
    }
}




