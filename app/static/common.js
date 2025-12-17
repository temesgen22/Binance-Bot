/**
 * Common JavaScript functions for Binance Bot GUI pages
 */

/**
 * Load and display current user information
 */
async function loadUserInfo() {
    try {
        const user = await AuthAPI.getCurrentUser();
        const userInfo = document.getElementById('user-info');
        if (userInfo) {
            userInfo.textContent = `👤 ${user.username}`;
        }
    } catch (e) {
        console.error('Failed to load user info:', e);
    }
}

/**
 * Initialize common page functionality
 * Call this in DOMContentLoaded event
 */
function initCommonPage() {
    // Check authentication
    if (typeof requireAuth === 'function') {
        requireAuth();
    }
    
    // Load user info if authenticated
    if (typeof Auth !== 'undefined' && Auth.isAuthenticated()) {
        loadUserInfo();
    }
}

// Auto-initialize if DOM is already loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCommonPage);
} else {
    // DOM already loaded
    initCommonPage();
}

