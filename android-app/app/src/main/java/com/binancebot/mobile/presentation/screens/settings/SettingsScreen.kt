package com.binancebot.mobile.presentation.screens.settings

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Help
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import com.binancebot.mobile.presentation.theme.Spacing
import com.binancebot.mobile.presentation.viewmodel.AuthViewModel
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    navController: NavController,
    authViewModel: AuthViewModel = hiltViewModel(),
    settingsViewModel: com.binancebot.mobile.presentation.viewmodel.SettingsViewModel = hiltViewModel()
) {
    var showLogoutDialog by remember { mutableStateOf(false) }
    val currentUser by settingsViewModel.currentUser.collectAsState()
    val themeMode by settingsViewModel.themeMode.collectAsState(initial = "auto")
    val notificationsEnabled by settingsViewModel.notificationsEnabled.collectAsState(initial = true)
    val language by settingsViewModel.language.collectAsState(initial = "en")
    val uiState by settingsViewModel.uiState.collectAsState()
    
    val scope = rememberCoroutineScope()
    
    // Dialog state variables
    var showProfileDialog by remember { mutableStateOf(false) }
    var showChangePasswordDialog by remember { mutableStateOf(false) }
    var showThemeDialog by remember { mutableStateOf(false) }
    var showLanguageDialog by remember { mutableStateOf(false) }
    
    val snackbarHostState = remember { SnackbarHostState() }
    
    // Show error message if any
    (uiState as? com.binancebot.mobile.presentation.viewmodel.SettingsUiState.Error)?.let { errorState ->
        LaunchedEffect(errorState) {
            snackbarHostState.showSnackbar(
                message = errorState.message,
                duration = SnackbarDuration.Long
            )
        }
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(Spacing.ScreenPadding),
            verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
        ) {
            // Account Section
            Card(
                modifier = Modifier.fillMaxWidth(),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(Spacing.CardPadding),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    Text(
                        text = "Account",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    HorizontalDivider()
                    
                    // User Info Display
                    currentUser?.let { user ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = Spacing.Small),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                Icons.Default.Person,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.size(24.dp)
                            )
                            Spacer(modifier = Modifier.width(Spacing.Medium))
                            Column {
                                Text(
                                    text = user.username,
                                    style = MaterialTheme.typography.bodyLarge,
                                    fontWeight = FontWeight.Medium
                                )
                                Text(
                                    text = user.email,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                        HorizontalDivider()
                    }
                    
                    SettingsItem(
                        icon = Icons.Default.Person,
                        title = "Edit Profile",
                        subtitle = "Update your profile information",
                        onClick = { showProfileDialog = true }
                    )
                    
                    SettingsItem(
                        icon = Icons.Default.Lock,
                        title = "Change Password",
                        subtitle = "Update your password",
                        onClick = { showChangePasswordDialog = true }
                    )
                }
            }
            
            // Preferences Section
            Card(
                modifier = Modifier.fillMaxWidth(),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(Spacing.CardPadding),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    Text(
                        text = "Preferences",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    HorizontalDivider()
                    
                    SettingsItem(
                        icon = Icons.Default.Notifications,
                        title = "Notifications",
                        subtitle = "Enable push notifications",
                        onClick = { 
                            scope.launch {
                                settingsViewModel.setNotificationsEnabled(!notificationsEnabled)
                            }
                        },
                        trailing = {
                            Switch(
                                checked = notificationsEnabled,
                                onCheckedChange = { enabled ->
                                    scope.launch {
                                        settingsViewModel.setNotificationsEnabled(enabled)
                                    }
                                }
                            )
                        }
                    )
                    
                    // Theme Mode Selection
                    SettingsItem(
                        icon = Icons.Default.DarkMode,
                        title = "Theme",
                        subtitle = when (themeMode) {
                            "light" -> "Light Mode"
                            "dark" -> "Dark Mode"
                            else -> "Follow System"
                        },
                        onClick = { showThemeDialog = true }
                    )
                    
                    // Language Selection
                    SettingsItem(
                        icon = Icons.Default.Language,
                        title = "Language",
                        subtitle = when (language) {
                            "en" -> "English"
                            "es" -> "Español"
                            "fr" -> "Français"
                            else -> "English"
                        },
                        onClick = { showLanguageDialog = true }
                    )
                }
            }
            
            // About Section
            Card(
                modifier = Modifier.fillMaxWidth(),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(Spacing.CardPadding),
                    verticalArrangement = Arrangement.spacedBy(Spacing.Small)
                ) {
                    Text(
                        text = "About",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    HorizontalDivider()
                    
                    SettingsItem(
                        icon = Icons.Default.Info,
                        title = "App Version",
                        subtitle = "1.0.0",
                        onClick = { }
                    )
                    
                    SettingsItem(
                        icon = Icons.AutoMirrored.Filled.Help,
                        title = "Help & Support",
                        subtitle = "Get help and contact support",
                        onClick = { 
                            navController.navigate("help")
                        }
                    )
                    
                    SettingsItem(
                        icon = Icons.Default.PrivacyTip,
                        title = "Data & Privacy",
                        subtitle = "Privacy settings and data management",
                        onClick = { 
                            navController.navigate("data_privacy")
                        }
                    )
                }
            }
            
            Spacer(modifier = Modifier.height(Spacing.Medium))
            
            // Logout Button
            Button(
                onClick = { showLogoutDialog = true },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.error
                )
            ) {
                Icon(Icons.AutoMirrored.Filled.Logout, null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(Spacing.Small))
                Text("Logout")
            }
        }
    }
    
    // Logout Confirmation Dialog
    if (showLogoutDialog) {
        AlertDialog(
            onDismissRequest = { showLogoutDialog = false },
            title = { Text("Logout") },
            text = { Text("Are you sure you want to logout?") },
            confirmButton = {
                Button(
                    onClick = {
                        authViewModel.logout()
                        navController.navigate("login") {
                            popUpTo(0)
                        }
                        showLogoutDialog = false
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Text("Logout")
                }
            },
            dismissButton = {
                TextButton(onClick = { showLogoutDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }
    
    // Profile Edit Dialog
    if (showProfileDialog) {
        EditProfileDialog(
            currentUser = currentUser,
            onDismiss = { showProfileDialog = false },
            onSave = { username, email ->
                settingsViewModel.updateProfile(username, email)
                showProfileDialog = false
            },
            isLoading = uiState is com.binancebot.mobile.presentation.viewmodel.SettingsUiState.Loading
        )
    }
    
    // Change Password Dialog
    if (showChangePasswordDialog) {
        ChangePasswordDialog(
            onDismiss = { showChangePasswordDialog = false },
            onChangePassword = { oldPassword, newPassword ->
                settingsViewModel.changePassword(oldPassword, newPassword)
                showChangePasswordDialog = false
            },
            isLoading = uiState is com.binancebot.mobile.presentation.viewmodel.SettingsUiState.Loading
        )
    }
    
    // Theme Selection Dialog
    if (showThemeDialog) {
        ThemeSelectionDialog(
            currentTheme = themeMode,
            onDismiss = { showThemeDialog = false },
            onThemeSelected = { mode ->
                scope.launch {
                    settingsViewModel.setThemeMode(mode)
                }
                showThemeDialog = false
            }
        )
    }
    
    // Language Selection Dialog
    if (showLanguageDialog) {
        LanguageSelectionDialog(
            currentLanguage = language,
            onDismiss = { showLanguageDialog = false },
            onLanguageSelected = { lang ->
                scope.launch {
                    settingsViewModel.setLanguage(lang)
                }
                showLanguageDialog = false
            }
        )
    }
    
    // Show error message if any
    (uiState as? com.binancebot.mobile.presentation.viewmodel.SettingsUiState.Error)?.let { errorState ->
        LaunchedEffect(errorState) {
            snackbarHostState.showSnackbar(
                message = errorState.message,
                duration = SnackbarDuration.Long
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EditProfileDialog(
    currentUser: com.binancebot.mobile.data.remote.dto.UserResponse?,
    onDismiss: () -> Unit,
    onSave: (String, String) -> Unit,
    isLoading: Boolean = false
) {
    var username by remember { mutableStateOf(currentUser?.username ?: "") }
    var email by remember { mutableStateOf(currentUser?.email ?: "") }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Edit Profile") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                OutlinedTextField(
                    value = username,
                    onValueChange = { username = it },
                    label = { Text("Username") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    leadingIcon = {
                        Icon(Icons.Default.Person, contentDescription = null)
                    },
                    enabled = !isLoading
                )
                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text("Email") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    leadingIcon = {
                        Icon(Icons.Default.Email, contentDescription = null)
                    },
                    enabled = !isLoading
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    if (username.isNotBlank() && email.isNotBlank()) {
                        onSave(username, email)
                    }
                },
                enabled = username.isNotBlank() && email.isNotBlank() && !isLoading
            ) {
                if (isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("Save")
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChangePasswordDialog(
    onDismiss: () -> Unit,
    onChangePassword: (String, String) -> Unit,
    isLoading: Boolean = false
) {
    var oldPassword by remember { mutableStateOf("") }
    var newPassword by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var showOldPassword by remember { mutableStateOf(false) }
    var showNewPassword by remember { mutableStateOf(false) }
    var showConfirmPassword by remember { mutableStateOf(false) }
    
    val passwordsMatch = newPassword == confirmPassword && newPassword.isNotBlank()
    val isValid = oldPassword.isNotBlank() && newPassword.isNotBlank() && passwordsMatch && newPassword.length >= 8
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Change Password") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(Spacing.Medium)
            ) {
                OutlinedTextField(
                    value = oldPassword,
                    onValueChange = { oldPassword = it },
                    label = { Text("Current Password") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    visualTransformation = if (showOldPassword) {
                        androidx.compose.ui.text.input.VisualTransformation.None
                    } else {
                        PasswordVisualTransformation()
                    },
                    trailingIcon = {
                        IconButton(onClick = { showOldPassword = !showOldPassword }) {
                            Icon(
                                imageVector = if (showOldPassword) Icons.Default.Visibility else Icons.Default.VisibilityOff,
                                contentDescription = if (showOldPassword) "Hide" else "Show"
                            )
                        }
                    }
                )
                OutlinedTextField(
                    value = newPassword,
                    onValueChange = { newPassword = it },
                    label = { Text("New Password") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    visualTransformation = if (showNewPassword) {
                        androidx.compose.ui.text.input.VisualTransformation.None
                    } else {
                        PasswordVisualTransformation()
                    },
                    trailingIcon = {
                        IconButton(onClick = { showNewPassword = !showNewPassword }) {
                            Icon(
                                imageVector = if (showNewPassword) Icons.Default.Visibility else Icons.Default.VisibilityOff,
                                contentDescription = if (showNewPassword) "Hide" else "Show"
                            )
                        }
                    },
                    isError = newPassword.isNotBlank() && newPassword.length < 8,
                    supportingText = {
                        if (newPassword.isNotBlank() && newPassword.length < 8) {
                            Text("Password must be at least 8 characters")
                        }
                    }
                )
                OutlinedTextField(
                    value = confirmPassword,
                    onValueChange = { confirmPassword = it },
                    label = { Text("Confirm New Password") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    visualTransformation = if (showConfirmPassword) {
                        androidx.compose.ui.text.input.VisualTransformation.None
                    } else {
                        PasswordVisualTransformation()
                    },
                    trailingIcon = {
                        IconButton(onClick = { showConfirmPassword = !showConfirmPassword }) {
                            Icon(
                                imageVector = if (showConfirmPassword) Icons.Default.Visibility else Icons.Default.VisibilityOff,
                                contentDescription = if (showConfirmPassword) "Hide" else "Show"
                            )
                        }
                    },
                    isError = confirmPassword.isNotBlank() && !passwordsMatch,
                    supportingText = {
                        if (confirmPassword.isNotBlank() && !passwordsMatch) {
                            Text("Passwords do not match")
                        }
                    }
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    if (isValid) {
                        onChangePassword(oldPassword, newPassword)
                    }
                },
                    enabled = isValid && !isLoading
            ) {
                if (isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("Change Password")
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

@Composable
fun ThemeSelectionDialog(
    currentTheme: String,
    onDismiss: () -> Unit,
    onThemeSelected: (String) -> Unit
) {
    val themes = listOf(
        "auto" to "Follow System",
        "light" to "Light Mode",
        "dark" to "Dark Mode"
    )
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Select Theme") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                themes.forEach { (mode, label) ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onThemeSelected(mode) }
                            .padding(vertical = Spacing.Small),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        RadioButton(
                            selected = currentTheme == mode,
                            onClick = { onThemeSelected(mode) }
                        )
                        Spacer(modifier = Modifier.width(Spacing.Small))
                        Text(
                            text = label,
                            style = MaterialTheme.typography.bodyLarge
                        )
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text("Close")
            }
        }
    )
}

@Composable
fun LanguageSelectionDialog(
    currentLanguage: String,
    onDismiss: () -> Unit,
    onLanguageSelected: (String) -> Unit
) {
    val languages = listOf(
        "en" to "English",
        "es" to "Español",
        "fr" to "Français",
        "de" to "Deutsch",
        "zh" to "中文"
    )
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Select Language") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(Spacing.Small)
            ) {
                languages.forEach { (code, name) ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onLanguageSelected(code) }
                            .padding(vertical = Spacing.Small),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        RadioButton(
                            selected = currentLanguage == code,
                            onClick = { onLanguageSelected(code) }
                        )
                        Spacer(modifier = Modifier.width(Spacing.Small))
                        Text(
                            text = name,
                            style = MaterialTheme.typography.bodyLarge
                        )
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text("Close")
            }
        }
    )
}

@Composable
fun SettingsItem(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    title: String,
    subtitle: String,
    onClick: () -> Unit,
    trailing: @Composable (() -> Unit)? = null
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = Spacing.Small),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(
            modifier = Modifier.weight(1f),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(24.dp)
            )
            Spacer(modifier = Modifier.width(Spacing.Medium))
            Column {
                Text(
                    text = title,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium
                )
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
        trailing?.invoke() ?: Icon(
            imageVector = Icons.Default.ChevronRight,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}
