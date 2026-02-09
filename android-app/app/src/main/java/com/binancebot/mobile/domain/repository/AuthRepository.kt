package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.ChangePasswordRequest
import com.binancebot.mobile.data.remote.dto.LoginRequest
import com.binancebot.mobile.data.remote.dto.LoginResponse
import com.binancebot.mobile.data.remote.dto.RegisterRequest
import com.binancebot.mobile.data.remote.dto.RegisterResponse
import com.binancebot.mobile.data.remote.dto.UpdateProfileRequest
import com.binancebot.mobile.data.remote.dto.UserResponse

/**
 * Repository interface for Authentication operations.
 */
interface AuthRepository {
    suspend fun login(request: LoginRequest): Result<LoginResponse>
    suspend fun register(request: RegisterRequest): Result<RegisterResponse>
    suspend fun getCurrentUser(): Result<UserResponse>
    suspend fun updateProfile(request: UpdateProfileRequest): Result<UserResponse>
    suspend fun changePassword(request: ChangePasswordRequest): Result<Unit>
}


