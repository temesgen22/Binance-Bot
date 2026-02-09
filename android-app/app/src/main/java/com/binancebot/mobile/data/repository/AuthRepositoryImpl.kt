package com.binancebot.mobile.data.repository

import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.LoginRequest
import com.binancebot.mobile.data.remote.dto.LoginResponse
import com.binancebot.mobile.data.remote.dto.RegisterRequest
import com.binancebot.mobile.data.remote.dto.RegisterResponse
import com.binancebot.mobile.domain.repository.AuthRepository
import com.binancebot.mobile.util.retryApiCall
import com.binancebot.mobile.util.toResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepositoryImpl @Inject constructor(
    private val api: BinanceBotApi
) : AuthRepository {
    
    override suspend fun login(request: LoginRequest): Result<LoginResponse> {
        return retryApiCall {
            val response = api.login(request)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun register(request: RegisterRequest): Result<RegisterResponse> {
        return retryApiCall {
            val response = api.register(request)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun getCurrentUser(): Result<com.binancebot.mobile.data.remote.dto.UserResponse> {
        return retryApiCall {
            val response = api.getCurrentUser()
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun updateProfile(request: com.binancebot.mobile.data.remote.dto.UpdateProfileRequest): Result<com.binancebot.mobile.data.remote.dto.UserResponse> {
        return retryApiCall {
            val response = api.updateProfile(request)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(it.data)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
    
    override suspend fun changePassword(request: com.binancebot.mobile.data.remote.dto.ChangePasswordRequest): Result<Unit> {
        return retryApiCall {
            val response = api.changePassword(request)
            response.toResult()
        }.let {
            when (it) {
                is com.binancebot.mobile.util.ApiResult.Success -> Result.success(Unit)
                is com.binancebot.mobile.util.ApiResult.Error -> Result.failure(Exception(it.message))
                is com.binancebot.mobile.util.ApiResult.Exception -> Result.failure(it.throwable)
            }
        }
    }
}


