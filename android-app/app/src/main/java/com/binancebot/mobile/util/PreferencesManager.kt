package com.binancebot.mobile.util

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.doublePreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.settingsDataStore: DataStore<Preferences> by preferencesDataStore(name = "app_settings")

@Singleton
class PreferencesManager @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val dataStore = context.settingsDataStore
    
    companion object {
        private val THEME_MODE_KEY = stringPreferencesKey("theme_mode") // "light", "dark", "auto"
        private val NOTIFICATIONS_ENABLED_KEY = booleanPreferencesKey("notifications_enabled")
        private val LANGUAGE_KEY = stringPreferencesKey("language") // "en", "es", etc.
        
        // Granular notification preferences
        private val TRADES_ENABLED_KEY = booleanPreferencesKey("trades_enabled")
        private val ALERTS_ENABLED_KEY = booleanPreferencesKey("alerts_enabled")
        private val STRATEGY_ENABLED_KEY = booleanPreferencesKey("strategy_enabled")
        private val SYSTEM_ENABLED_KEY = booleanPreferencesKey("system_enabled")
        private val SOUND_ENABLED_KEY = booleanPreferencesKey("sound_enabled")
        private val VIBRATION_ENABLED_KEY = booleanPreferencesKey("vibration_enabled")
        private val TRADE_PNL_THRESHOLD_KEY = doublePreferencesKey("trade_pnl_threshold")
        private val ALERT_PRIORITY_KEY = intPreferencesKey("alert_priority")
    }
    
    // Theme Mode
    val themeMode: Flow<String> = dataStore.data.map { preferences ->
        preferences[THEME_MODE_KEY] ?: "auto"
    }
    
    suspend fun setThemeMode(mode: String) {
        dataStore.edit { preferences ->
            preferences[THEME_MODE_KEY] = mode
        }
    }
    
    // Notifications
    val notificationsEnabled: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[NOTIFICATIONS_ENABLED_KEY] ?: true
    }
    
    suspend fun setNotificationsEnabled(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[NOTIFICATIONS_ENABLED_KEY] = enabled
        }
    }
    
    // Language
    val language: Flow<String> = dataStore.data.map { preferences ->
        preferences[LANGUAGE_KEY] ?: "en"
    }
    
    suspend fun setLanguage(lang: String) {
        dataStore.edit { preferences ->
            preferences[LANGUAGE_KEY] = lang
        }
    }
    
    // Granular Notification Preferences
    
    val tradesEnabled: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[TRADES_ENABLED_KEY] ?: true
    }
    
    suspend fun setTradesEnabled(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[TRADES_ENABLED_KEY] = enabled
        }
    }
    
    val alertsEnabled: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[ALERTS_ENABLED_KEY] ?: true
    }
    
    suspend fun setAlertsEnabled(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[ALERTS_ENABLED_KEY] = enabled
        }
    }
    
    val strategyEnabled: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[STRATEGY_ENABLED_KEY] ?: true
    }
    
    suspend fun setStrategyEnabled(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[STRATEGY_ENABLED_KEY] = enabled
        }
    }
    
    val systemEnabled: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[SYSTEM_ENABLED_KEY] ?: false
    }
    
    suspend fun setSystemEnabled(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[SYSTEM_ENABLED_KEY] = enabled
        }
    }
    
    val soundEnabled: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[SOUND_ENABLED_KEY] ?: true
    }
    
    suspend fun setSoundEnabled(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[SOUND_ENABLED_KEY] = enabled
        }
    }
    
    val vibrationEnabled: Flow<Boolean> = dataStore.data.map { preferences ->
        preferences[VIBRATION_ENABLED_KEY] ?: true
    }
    
    suspend fun setVibrationEnabled(enabled: Boolean) {
        dataStore.edit { preferences ->
            preferences[VIBRATION_ENABLED_KEY] = enabled
        }
    }
    
    val tradePnLThreshold: Flow<Double> = dataStore.data.map { preferences ->
        preferences[TRADE_PNL_THRESHOLD_KEY] ?: 100.0
    }
    
    suspend fun setTradePnLThreshold(threshold: Double) {
        dataStore.edit { preferences ->
            preferences[TRADE_PNL_THRESHOLD_KEY] = threshold
        }
    }
    
    val alertPriority: Flow<Int> = dataStore.data.map { preferences ->
        preferences[ALERT_PRIORITY_KEY] ?: 0
    }
    
    suspend fun setAlertPriority(priority: Int) {
        dataStore.edit { preferences ->
            preferences[ALERT_PRIORITY_KEY] = priority
        }
    }
}



