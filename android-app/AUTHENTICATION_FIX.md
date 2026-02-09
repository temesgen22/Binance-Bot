# Authentication Fix - 403 Forbidden Error

## Problem
The Android app was getting **403 Forbidden** errors when trying to fetch strategies:
```
GET /api/strategies/list HTTP/1.1" 403 Forbidden
```

## Root Cause
The Android app was using `TokenAuthenticator` which only adds the Authorization header when the server returns a 401 (Unauthorized) error. However, for initial requests, the Authorization header with the Bearer token was not being added, causing the backend to reject requests with 403 Forbidden.

## Solution
Created an `AuthInterceptor` that adds the Authorization header to **all** API requests upfront, before they are sent to the server.

### Changes Made

1. **Created `AuthInterceptor.kt`**
   - Interceptor that adds `Authorization: Bearer {token}` header to all requests
   - Gets the access token from `TokenManager`
   - Only adds header if token exists

2. **Updated `NetworkModule.kt`**
   - Added `AuthInterceptor` as a dependency
   - Added interceptor to OkHttpClient **before** the `TokenAuthenticator`
   - Order matters: Interceptor adds token, Authenticator refreshes on 401

### How It Works

1. **AuthInterceptor** (runs first):
   - Adds `Authorization: Bearer {accessToken}` to all requests
   - If no token exists, request proceeds without header

2. **TokenAuthenticator** (runs on 401):
   - If server returns 401, automatically refreshes token
   - Retries request with new token

### Request Flow

```
Request → AuthInterceptor (adds token) → Server
                                    ↓
                              If 401 Unauthorized
                                    ↓
                          TokenAuthenticator (refreshes token)
                                    ↓
                          Retry with new token
```

## Testing

After this fix, the Android app should:
1. ✅ Successfully authenticate all API requests
2. ✅ Fetch strategies list without 403 errors
3. ✅ Automatically refresh tokens when they expire
4. ✅ Handle authentication errors gracefully

## Files Changed

- `android-app/app/src/main/java/com/binancebot/mobile/data/remote/api/AuthInterceptor.kt` (new)
- `android-app/app/src/main/java/com/binancebot/mobile/di/NetworkModule.kt` (updated)



























