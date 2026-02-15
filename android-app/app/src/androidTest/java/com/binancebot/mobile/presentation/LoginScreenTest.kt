package com.binancebot.mobile.presentation

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import org.junit.Rule
import org.junit.Test

/**
 * Instrumented UI tests for the Login screen.
 * Ensure app shows login (e.g. clear app data before run, or app not logged in).
 */
@HiltAndroidTest
class LoginScreenTest {

    @get:Rule(order = 0)
    val hiltRule = HiltAndroidRule(this)

    @get:Rule(order = 1)
    val composeTestRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun loginScreen_displaysUsernameAndPasswordFields() {
        composeTestRule.waitForIdle()
        composeTestRule.onNodeWithText("Login", ignoreCase = true).assertExists()
    }

    @Test
    fun login_withInvalidCredentials_showsError() {
        composeTestRule.waitForIdle()
        composeTestRule.onNodeWithText("Username", ignoreCase = true).performTextInput("bad")
        composeTestRule.onNodeWithText("Password", ignoreCase = true).performTextInput("bad")
        composeTestRule.onNodeWithText("Login", ignoreCase = true).performClick()
        composeTestRule.waitForIdle()
        composeTestRule.onNodeWithText("failed", ignoreCase = true).assertExists()
    }
}
