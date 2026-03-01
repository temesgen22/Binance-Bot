package com.binancebot.mobile.util

import android.util.Log
import com.binancebot.mobile.BuildConfig

/**
 * Central logger that only emits in debug builds.
 * Use instead of Log.d/Log.e in production code paths (P0.2 CODE_QUALITY_IMPROVEMENT_PLAN).
 * Avoid logging tokens, strategy IDs, or PII; redact if needed.
 */
object AppLogger {

    @JvmStatic
    fun d(tag: String, message: String) {
        if (BuildConfig.DEBUG) {
            Log.d(tag, message)
        }
    }

    @JvmStatic
    fun e(tag: String, message: String) {
        if (BuildConfig.DEBUG) {
            Log.e(tag, message)
        }
    }

    @JvmStatic
    fun e(tag: String, message: String, throwable: Throwable?) {
        if (BuildConfig.DEBUG) {
            Log.e(tag, message, throwable)
        }
    }

    @JvmStatic
    fun w(tag: String, message: String) {
        if (BuildConfig.DEBUG) {
            Log.w(tag, message)
        }
    }

    @JvmStatic
    fun i(tag: String, message: String) {
        if (BuildConfig.DEBUG) {
            Log.i(tag, message)
        }
    }
}
