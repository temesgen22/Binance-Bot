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
 * Initialize mobile menu toggle
 */
function initMobileMenu() {
    const menuToggle = document.querySelector('.menu-toggle');
    const navLinks = document.querySelector('.nav-links');
    
    if (menuToggle && navLinks) {
        menuToggle.addEventListener('click', function() {
            navLinks.classList.toggle('active');
            // Update button text/icon
            const isActive = navLinks.classList.contains('active');
            menuToggle.textContent = isActive ? '✕' : '☰';
            menuToggle.setAttribute('aria-expanded', isActive);
        });
        
        // Close menu when clicking outside
        document.addEventListener('click', function(event) {
            if (navLinks.classList.contains('active') && 
                !navLinks.contains(event.target) && 
                !menuToggle.contains(event.target)) {
                navLinks.classList.remove('active');
                menuToggle.textContent = '☰';
                menuToggle.setAttribute('aria-expanded', 'false');
            }
        });
        
        // Close menu when clicking a nav link on mobile
        navLinks.addEventListener('click', function(event) {
            if (event.target.tagName === 'A' && window.innerWidth <= 575.98) {
                navLinks.classList.remove('active');
                menuToggle.textContent = '☰';
                menuToggle.setAttribute('aria-expanded', 'false');
            }
        });
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
    
    // Initialize mobile menu
    initMobileMenu();
}

// Auto-initialize if DOM is already loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCommonPage);
} else {
    // DOM already loaded
    initCommonPage();
}

