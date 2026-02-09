package com.binancebot.mobile.util

object Constants {
    // TODO: Update with your backend URL
    const val BASE_URL = "http://95.216.216.26/api/" // Production Backend
    
    // API Endpoints
    const val AUTH_LOGIN = "auth/login"
    const val AUTH_REGISTER = "auth/register"
    const val AUTH_REFRESH = "auth/refresh"
    
    // Preferences Keys
    const val PREF_ACCESS_TOKEN = "access_token"
    const val PREF_REFRESH_TOKEN = "refresh_token"
    const val PREF_USER_ID = "user_id"
    const val PREF_USERNAME = "username"
    
    // Network
    const val CONNECT_TIMEOUT = 30L
    const val READ_TIMEOUT = 30L
    const val WRITE_TIMEOUT = 30L
}






























