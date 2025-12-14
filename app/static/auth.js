/**
 * Authentication utility for frontend
 * Handles JWT token storage and API request authentication
 */

const AUTH_STORAGE_KEY = 'binance_bot_auth';
const TOKEN_STORAGE_KEY = 'binance_bot_token';
const REFRESH_TOKEN_STORAGE_KEY = 'binance_bot_refresh_token';

/**
 * Auth API - handles authentication-related API calls
 */
const AuthAPI = {
    /**
     * Register a new user
     */
    async register(username, email, password, fullName = null) {
        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username,
                email,
                password,
                full_name: fullName
            })
        });
        
        if (!response.ok) {
            let error;
            try {
                error = await response.json();
            } catch (e) {
                const text = await response.text();
                throw new Error(text || `Registration failed: ${response.status} ${response.statusText}`);
            }
            throw new Error(error.detail || error.message || 'Registration failed');
        }
        
        return await response.json();
    },
    
    /**
     * Login and get tokens
     */
    async login(username, password) {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
        }
        
        const data = await response.json();
        Auth.setTokens(data.access_token, data.refresh_token);
        return data;
    },
    
    /**
     * Refresh access token
     */
    async refresh() {
        const refreshToken = Auth.getRefreshToken();
        if (!refreshToken) {
            throw new Error('No refresh token available');
        }
        
        const response = await fetch('/api/auth/refresh', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken })
        });
        
        if (!response.ok) {
            Auth.clearTokens();
            throw new Error('Token refresh failed');
        }
        
        const data = await response.json();
        Auth.setTokens(data.access_token, data.refresh_token);
        return data;
    },
    
    /**
     * Get current user info
     */
    async getCurrentUser() {
        const token = Auth.getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }
        
        const response = await fetch('/api/auth/me', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (!response.ok) {
            if (response.status === 401) {
                // Token expired, try refresh
                try {
                    await AuthAPI.refresh();
                    return await AuthAPI.getCurrentUser();
                } catch (e) {
                    Auth.clearTokens();
                    throw new Error('Session expired');
                }
            }
            throw new Error('Failed to get user info');
        }
        
        return await response.json();
    },
    
    /**
     * Logout
     */
    async logout() {
        Auth.clearTokens();
        return { message: 'Logged out successfully' };
    }
};

/**
 * Auth - token management
 */
const Auth = {
    /**
     * Set tokens in localStorage
     */
    setTokens(accessToken, refreshToken) {
        localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
        localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, refreshToken);
        localStorage.setItem(AUTH_STORAGE_KEY, 'true');
    },
    
    /**
     * Get access token
     */
    getToken() {
        return localStorage.getItem(TOKEN_STORAGE_KEY);
    },
    
    /**
     * Get refresh token
     */
    getRefreshToken() {
        return localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
    },
    
    /**
     * Check if user is authenticated
     */
    isAuthenticated() {
        return !!this.getToken();
    },
    
    /**
     * Clear tokens
     */
    clearTokens() {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
        localStorage.removeItem(AUTH_STORAGE_KEY);
    },
    
    /**
     * Get auth headers for API requests
     */
    getAuthHeaders() {
        const token = this.getToken();
        if (!token) {
            return {};
        }
        return {
            'Authorization': `Bearer ${token}`
        };
    }
};

/**
 * Authenticated fetch - automatically adds auth headers and handles token refresh
 */
async function authFetch(url, options = {}) {
    // Add auth headers
    const headers = {
        ...Auth.getAuthHeaders(),
        ...(options.headers || {})
    };
    
    // Ensure Content-Type is set for JSON requests
    if (options.body && typeof options.body === 'object' && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(options.body);
    }
    
    options.headers = headers;
    
    let response = await fetch(url, options);
    
    // If 401, try to refresh token and retry
    if (response.status === 401 && Auth.getRefreshToken()) {
        try {
            await AuthAPI.refresh();
            // Retry with new token
            options.headers = {
                ...Auth.getAuthHeaders(),
                ...(options.headers || {})
            };
            response = await fetch(url, options);
        } catch (e) {
            // Refresh failed, redirect to login
            Auth.clearTokens();
            if (window.location.pathname !== '/login.html' && window.location.pathname !== '/register.html') {
                window.location.href = '/login.html';
            }
            throw new Error('Session expired');
        }
    }
    
    return response;
}

/**
 * Check authentication and redirect to login if not authenticated
 * This should be called immediately when the page loads
 */
function requireAuth() {
    if (!Auth.isAuthenticated()) {
        // Prevent any further execution
        window.location.replace('/login.html');
        return false;
    }
    return true;
}

/**
 * Global logout function that can be called from any page
 */
async function logout() {
    try {
        await AuthAPI.logout();
    } catch (e) {
        console.error('Logout error:', e);
    }
    // Clear tokens and redirect regardless of API call success
    Auth.clearTokens();
    window.location.replace('/login.html');
}

// Make logout available globally
window.logout = logout;

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Auth, AuthAPI, authFetch, requireAuth };
}

