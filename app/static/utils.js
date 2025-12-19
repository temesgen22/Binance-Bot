/**
 * Shared Utility Functions
 * Common formatting and utility functions used across multiple pages
 * to eliminate code duplication.
 */

/**
 * Format currency value with proper sign and decimal places.
 * Uses UserSettings if available, otherwise falls back to standard format.
 * 
 * @param {number|string|null|undefined} value - The value to format
 * @returns {string} Formatted currency string (e.g., "+$123.45" or "-$67.89")
 */
window.formatCurrency = function(value) {
    // Handle null/undefined/NaN
    if (value === null || value === undefined || isNaN(value)) {
        return '$0.00';
    }
    
    // Use UserSettings if available (respects user's currency symbol preference)
    if (typeof UserSettings !== 'undefined' && UserSettings.formatCurrency) {
        return UserSettings.formatCurrency(value);
    }
    
    // Fallback: Standard format with sign
    const numValue = parseFloat(value);
    const sign = numValue >= 0 ? '+' : '';
    return sign + '$' + Math.abs(numValue).toFixed(2);
};

/**
 * Format date/time string to readable format.
 * Uses UserSettings if available, otherwise falls back to UTC format.
 * 
 * @param {string|null|undefined} dateString - ISO date string or null
 * @returns {string} Formatted date string or 'N/A' if invalid
 */
window.formatDateTime = function(dateString) {
    // Use UserSettings if available (respects user's date format preference)
    if (typeof UserSettings !== 'undefined' && UserSettings.formatDate) {
        return UserSettings.formatDate(dateString);
    }
    
    // Fallback: UTC format
    if (!dateString) return 'N/A';
    
    try {
        const date = new Date(dateString);
        if (isNaN(date.getTime())) {
            console.warn('Invalid date string:', dateString);
            return 'Invalid Date';
        }
        const year = date.getUTCFullYear();
        const month = String(date.getUTCMonth() + 1).padStart(2, '0');
        const day = String(date.getUTCDate()).padStart(2, '0');
        const hours = String(date.getUTCHours()).padStart(2, '0');
        const minutes = String(date.getUTCMinutes()).padStart(2, '0');
        const seconds = String(date.getUTCSeconds()).padStart(2, '0');
        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds} UTC`;
    } catch (e) {
        console.error('Error formatting date:', e);
        return 'Invalid Date';
    }
};

/**
 * Format date for datetime-local input (YYYY-MM-DDTHH:mm or YYYY-MM-DDTHH:mm:ss format).
 * Used for date/time input fields.
 * 
 * @param {Date|string} date - Date object or date string
 * @param {boolean} includeSeconds - Whether to include seconds in output (default: false)
 * @returns {string} Formatted string for datetime-local input
 */
window.formatDateTimeLocal = function(date, includeSeconds = false) {
    if (!date) return '';
    
    const d = date instanceof Date ? date : new Date(date);
    if (isNaN(d.getTime())) {
        console.warn('Invalid date for formatDateTimeLocal:', date);
        return '';
    }
    
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    
    if (includeSeconds) {
        const seconds = String(d.getSeconds()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
    }
    
    return `${year}-${month}-${day}T${hours}:${minutes}`;
};

/**
 * Format percentage value with sign and decimal places.
 * 
 * @param {number|string} value - The percentage value (e.g., 0.05 for 5%)
 * @param {number} decimals - Number of decimal places (default: 2)
 * @returns {string} Formatted percentage string (e.g., "+5.00%" or "-2.50%")
 */
window.formatPercent = function(value, decimals = 2) {
    if (value === null || value === undefined || isNaN(value)) {
        return '0.00%';
    }
    
    const numValue = parseFloat(value);
    // Assume value is already a percentage (0-100 range), not a decimal (0-1 range)
    // If you need to convert from decimal, multiply by 100 before calling this function
    const sign = numValue >= 0 ? '+' : '';
    return sign + Math.abs(numValue).toFixed(decimals) + '%';
};

