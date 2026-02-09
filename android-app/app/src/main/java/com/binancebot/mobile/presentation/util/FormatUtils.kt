package com.binancebot.mobile.presentation.util

import java.text.NumberFormat
import java.util.*

object FormatUtils {
    private val currencyFormatter = NumberFormat.getCurrencyInstance(Locale.getDefault()).apply {
        maximumFractionDigits = 2
    }
    
    fun formatCurrency(amount: Double): String {
        return currencyFormatter.format(amount)
    }
    
    fun formatPercentage(value: Double, decimals: Int = 2): String {
        return String.format(Locale.getDefault(), "%.${decimals}f%%", value * 100)
    }
    
    fun formatNumber(value: Double, decimals: Int = 2): String {
        return String.format(Locale.getDefault(), "%.${decimals}f", value)
    }
}



