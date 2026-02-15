package com.binancebot.mobile.presentation.viewmodel

import android.content.Context
import app.cash.turbine.test
import com.binancebot.mobile.data.remote.dto.LoginRequest
import com.binancebot.mobile.data.remote.dto.LoginResponse
import com.binancebot.mobile.domain.repository.AuthRepository
import com.binancebot.mobile.domain.repository.NotificationRepository
import com.binancebot.mobile.util.TokenManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.mockito.Mock
import org.mockito.MockitoAnnotations
import org.mockito.kotlin.any
import org.mockito.kotlin.whenever
import kotlin.test.assertEquals

@OptIn(ExperimentalCoroutinesApi::class)
class AuthViewModelTest {

    @Mock
    lateinit var authRepository: AuthRepository

    @Mock
    lateinit var notificationRepository: NotificationRepository

    @Mock
    lateinit var tokenManager: TokenManager

    @Mock
    lateinit var context: Context

    private lateinit var viewModel: AuthViewModel
    private val testDispatcher = UnconfinedTestDispatcher()

    @Before
    fun setup() {
        MockitoAnnotations.openMocks(this)
        Dispatchers.setMain(testDispatcher)
        viewModel = AuthViewModel(authRepository, notificationRepository, tokenManager, context)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `login success updates uiState to Success`() = runTest {
        val response = LoginResponse(
            accessToken = "access",
            refreshToken = "refresh",
            tokenType = "Bearer"
        )
        whenever(authRepository.login(any<LoginRequest>())).thenReturn(Result.success(response))

        viewModel.uiState.test {
            viewModel.login("user", "pass")
            skipItems(1)
            assertEquals(AuthUiState.Loading, awaitItem())
            assertEquals(AuthUiState.Success, awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `login failure updates uiState to Error`() = runTest {
        whenever(authRepository.login(any<LoginRequest>())).thenReturn(
            Result.failure(RuntimeException("Bad credentials"))
        )

        viewModel.uiState.test {
            viewModel.login("user", "wrong")
            skipItems(1)
            assertEquals(AuthUiState.Loading, awaitItem())
            val error = awaitItem() as AuthUiState.Error
            assertEquals("Bad credentials", error.message)
            cancelAndIgnoreRemainingEvents()
        }
    }
}
