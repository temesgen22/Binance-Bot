package com.binancebot.mobile.presentation.components

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Error
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.binancebot.mobile.presentation.theme.Spacing

/**
 * Reusable error display component
 */
@Composable
fun ErrorHandler(
    message: String,
    onRetry: (() -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(Spacing.ScreenPadding),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            imageVector = Icons.Default.Error,
            contentDescription = null,
            modifier = Modifier.size(64.dp),
            tint = MaterialTheme.colorScheme.error
        )
        Spacer(modifier = Modifier.height(Spacing.Medium))
        Text(
            text = message,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurface,
            textAlign = TextAlign.Center
        )
        if (onRetry != null) {
            Spacer(modifier = Modifier.height(Spacing.Medium))
            Button(onClick = onRetry) {
                Text("Retry")
            }
        }
    }
}

/**
 * Network error handler with common error messages
 */
@Composable
fun NetworkErrorHandler(
    error: Throwable?,
    onRetry: (() -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    val errorMessage = when {
        error?.message?.contains("Unable to resolve host") == true -> 
            "No internet connection. Please check your network."
        error?.message?.contains("timeout") == true -> 
            "Request timed out. Please try again."
        error?.message?.contains("401") == true -> 
            "Authentication failed. Please login again."
        error?.message?.contains("404") == true -> 
            "Resource not found."
        error?.message?.contains("500") == true -> 
            "Server error. Please try again later."
        error != null -> error.message ?: "An error occurred"
        else -> "Unknown error"
    }
    
    ErrorHandler(
        message = errorMessage,
        onRetry = onRetry,
        modifier = modifier
    )
}

