package com.binancebot.mobile.util

import com.binancebot.mobile.data.remote.dto.ErrorResponse
import com.google.gson.Gson
import retrofit2.HttpException
import retrofit2.Response
import java.io.IOException
import java.net.SocketTimeoutException

/**
 * Unified API result wrapper for all network operations.
 * 
 * ✅ CRITICAL FIX: Provides consistent error handling across the app.
 */
sealed class ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>()
    data class Error(
        val code: Int,
        val message: String,
        val errorResponse: ErrorResponse? = null
    ) : ApiResult<Nothing>()
    data class Exception(val throwable: Throwable) : ApiResult<Nothing>()
    
    val isSuccess: Boolean get() = this is Success
    val isError: Boolean get() = this is Error
    val isException: Boolean get() = this is Exception
    
    inline fun <R> fold(
        onSuccess: (T) -> R,
        onError: (Error) -> R,
        onException: (Exception) -> R
    ): R = when (this) {
        is Success -> onSuccess(data)
        is Error -> onError(this)
        is Exception -> onException(this)
    }
}

/**
 * Error mapper for converting exceptions and HTTP errors to ApiResult.Error
 */
object ErrorMapper {
    private val gson = Gson()
    
    fun map(throwable: Throwable): ApiResult.Error {
        return when (throwable) {
            is HttpException -> {
                val errorBody = throwable.response()?.errorBody()?.string()
                val errorResponse = try {
                    gson.fromJson(errorBody, ErrorResponse::class.java)
                } catch (e: Exception) {
                    null
                }
                ApiResult.Error(
                    code = throwable.code(),
                    message = errorResponse?.message ?: throwable.message() ?: "Unknown error",
                    errorResponse = errorResponse
                )
            }
            is SocketTimeoutException -> {
                ApiResult.Error(
                    code = 408,
                    message = "Request timeout. Please check your connection."
                )
            }
            is IOException -> {
                ApiResult.Error(
                    code = 0,
                    message = "Network error. Please check your internet connection."
                )
            }
            else -> {
                ApiResult.Error(
                    code = 0,
                    message = throwable.message ?: "Unknown error occurred"
                )
            }
        }
    }
    
    fun map(response: Response<*>): ApiResult.Error {
        val errorBody = response.errorBody()?.string()
        val errorResponse = try {
            gson.fromJson(errorBody, ErrorResponse::class.java)
        } catch (e: Exception) {
            null
        }
        return ApiResult.Error(
            code = response.code(),
            message = errorResponse?.message ?: response.message() ?: "Unknown error",
            errorResponse = errorResponse
        )
    }
}

/**
 * Retry rules for determining when to retry API calls
 */
object RetryRules {
    fun shouldRetry(result: ApiResult<*>): Boolean {
        return when (result) {
            is ApiResult.Error -> {
                // Retry on 5xx errors or network errors
                result.code in 500..599 || result.code == 0
            }
            is ApiResult.Exception -> {
                // Retry on network exceptions
                result.throwable is IOException || result.throwable is SocketTimeoutException
            }
            else -> false
        }
    }
    
    fun getRetryDelay(attempt: Int): Long {
        // Exponential backoff: 1s, 2s, 4s (max 10s)
        return (1000L * (1 shl attempt)).coerceAtMost(10000L)
    }
}

/**
 * Extension function to convert Retrofit Response to ApiResult
 */
suspend fun <T> Response<T>.toResult(): ApiResult<T> {
    return try {
        if (isSuccessful && body() != null) {
            ApiResult.Success(body()!!)
        } else {
            ErrorMapper.map(this)
        }
    } catch (e: Exception) {
        ErrorMapper.map(e)
    }
}

/**
 * Extension function for retrying API calls with exponential backoff
 */
suspend fun <T> retryApiCall(
    maxRetries: Int = 3,
    block: suspend () -> ApiResult<T>
): ApiResult<T> {
    var lastResult: ApiResult<T>? = null
    
    for (attempt in 0 until maxRetries) {
        val result = block()
        
        if (result.isSuccess) {
            return result
        }
        
        lastResult = result
        
        if (RetryRules.shouldRetry(result) && attempt < maxRetries - 1) {
            val delay = RetryRules.getRetryDelay(attempt)
            kotlinx.coroutines.delay(delay)
        } else {
            break
        }
    }
    
    return lastResult ?: ApiResult.Exception(java.lang.Exception("Max retries exceeded"))
}



