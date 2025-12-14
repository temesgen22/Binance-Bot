/**
 * User Settings Management
 * Stores user preferences in localStorage
 */

const UserSettings = {
    // Default settings
    defaults: {
        timeFormat: 'utc', // 'utc' or 'local'
        dateFormat: 'iso', // 'iso', 'us', 'european', 'compact'
        showTimezone: true,
        decimalPlaces: 4,
        currencySymbol: '$',
        theme: 'light', // 'light' or 'dark'
        autoRefresh: false,
        refreshInterval: 30, // seconds
    },

    /**
     * Get all settings
     */
    getAll() {
        try {
            const stored = localStorage.getItem('userSettings');
            if (stored) {
                const parsed = JSON.parse(stored);
                return { ...this.defaults, ...parsed };
            }
        } catch (e) {
            console.warn('Error loading settings:', e);
        }
        return { ...this.defaults };
    },

    /**
     * Get a specific setting
     */
    get(key) {
        const settings = this.getAll();
        return settings[key] !== undefined ? settings[key] : this.defaults[key];
    },

    /**
     * Set a setting
     */
    set(key, value) {
        try {
            const settings = this.getAll();
            settings[key] = value;
            localStorage.setItem('userSettings', JSON.stringify(settings));
            return true;
        } catch (e) {
            console.error('Error saving setting:', e);
            return false;
        }
    },

    /**
     * Set multiple settings at once
     */
    setMultiple(settingsObj) {
        try {
            const current = this.getAll();
            const updated = { ...current, ...settingsObj };
            localStorage.setItem('userSettings', JSON.stringify(updated));
            return true;
        } catch (e) {
            console.error('Error saving settings:', e);
            return false;
        }
    },

    /**
     * Reset to defaults
     */
    reset() {
        try {
            localStorage.removeItem('userSettings');
            return true;
        } catch (e) {
            console.error('Error resetting settings:', e);
            return false;
        }
    },

    /**
     * Format date according to user settings
     */
    formatDate(dateString) {
        if (!dateString) return 'N/A';
        
        try {
            const date = new Date(dateString);
            if (isNaN(date.getTime())) {
                console.warn('Invalid date string:', dateString);
                return 'Invalid Date';
            }

            const timeFormat = this.get('timeFormat');
            const dateFormat = this.get('dateFormat');
            const showTimezone = this.get('showTimezone');

            let year, month, day, hours, minutes, seconds;
            
            if (timeFormat === 'utc') {
                year = date.getUTCFullYear();
                month = String(date.getUTCMonth() + 1).padStart(2, '0');
                day = String(date.getUTCDate()).padStart(2, '0');
                hours = String(date.getUTCHours()).padStart(2, '0');
                minutes = String(date.getUTCMinutes()).padStart(2, '0');
                seconds = String(date.getUTCSeconds()).padStart(2, '0');
            } else {
                year = date.getFullYear();
                month = String(date.getMonth() + 1).padStart(2, '0');
                day = String(date.getDate()).padStart(2, '0');
                hours = String(date.getHours()).padStart(2, '0');
                minutes = String(date.getMinutes()).padStart(2, '0');
                seconds = String(date.getSeconds()).padStart(2, '0');
            }

            let formattedDate;
            switch (dateFormat) {
                case 'us':
                    // MM/DD/YYYY HH:MM:SS
                    formattedDate = `${month}/${day}/${year} ${hours}:${minutes}:${seconds}`;
                    break;
                case 'european':
                    // DD/MM/YYYY HH:MM:SS
                    formattedDate = `${day}/${month}/${year} ${hours}:${minutes}:${seconds}`;
                    break;
                case 'compact':
                    // YYYYMMDD-HHMMSS
                    formattedDate = `${year}${month}${day}-${hours}${minutes}${seconds}`;
                    break;
                case 'iso':
                default:
                    // YYYY-MM-DD HH:MM:SS
                    formattedDate = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
                    break;
            }

            if (showTimezone) {
                const tzLabel = timeFormat === 'utc' ? 'UTC' : this.getTimezoneLabel();
                formattedDate += ` ${tzLabel}`;
            }

            return formattedDate;
        } catch (e) {
            console.warn('Error formatting date:', dateString, e);
            return 'Invalid Date';
        }
    },

    /**
     * Get timezone label for local time
     */
    getTimezoneLabel() {
        try {
            const offset = -new Date().getTimezoneOffset();
            const hours = Math.floor(Math.abs(offset) / 60);
            const minutes = Math.abs(offset) % 60;
            const sign = offset >= 0 ? '+' : '-';
            return `UTC${sign}${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
        } catch (e) {
            return 'Local';
        }
    },

    /**
     * Format currency according to user settings
     */
    formatCurrency(value) {
        const currencySymbol = this.get('currencySymbol');
        const sign = value >= 0 ? '+' : '';
        return `${sign}${currencySymbol}${Math.abs(value).toFixed(2)}`;
    },

    /**
     * Format number with configured decimal places
     */
    formatNumber(value, decimals = null) {
        const decimalPlaces = decimals !== null ? decimals : this.get('decimalPlaces');
        return parseFloat(value).toFixed(decimalPlaces);
    }
};

// Make it available globally
if (typeof window !== 'undefined') {
    window.UserSettings = UserSettings;
}

