package com.binancebot.mobile.domain.model

/**
 * Domain model for Log Entry.
 * This is the business logic model, separate from data layer.
 */
data class LogEntry(
    val id: String,
    val timestamp: Long,
    val level: String,
    val message: String,
    val symbol: String? = null
) {
    val isError: Boolean
        get() = level.uppercase() == "ERROR"
    
    val isWarning: Boolean
        get() = level.uppercase() == "WARNING"
    
    val isInfo: Boolean
        get() = level.uppercase() == "INFO"
    
    val isDebug: Boolean
        get() = level.uppercase() == "DEBUG"
}










































