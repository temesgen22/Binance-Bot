// Dashboard JavaScript

// Check authentication
(function() {
    if (!requireAuth()) {
        throw new Error('Not authenticated');
    }
})();

const API_BASE = '';

// Format duration in seconds to human-readable format (hours or minutes)
function formatDuration(seconds) {
    if (seconds === null || seconds === undefined || isNaN(seconds) || seconds < 0) {
        return 'N/A';
    }
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    
    if (hours > 0) {
        if (minutes > 0) {
            return `${hours}h ${minutes}m`;
        }
        return `${hours}h`;
    } else if (minutes > 0) {
        return `${minutes}m`;
    } else {
        return `${Math.floor(seconds)}s`;
    }
}

let currentTab = 'overview';
let currentFilters = {
    start_date: null,
    end_date: null,
    account_id: null
};

// Auto-refresh settings
let autoRefreshInterval = null;
let autoRefreshEnabled = false;
let autoRefreshIntervalMs = 30000; // Default: 30 seconds

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    loadOverview();
    loadAccounts();
    initializeAutoRefresh();
});

// Initialize auto-refresh controls
function initializeAutoRefresh() {
    // Add auto-refresh controls to the filter panel
    const filterPanel = document.querySelector('.filter-panel');
    if (filterPanel) {
        const refreshControls = document.createElement('div');
        refreshControls.className = 'filter-group';
        refreshControls.style.marginTop = '15px';
        refreshControls.innerHTML = `
            <label style="display: flex; align-items: center; gap: 10px;">
                <input type="checkbox" id="auto-refresh-toggle" onchange="toggleAutoRefresh()">
                <span>Auto-refresh (30s)</span>
            </label>
            <select id="refresh-interval" onchange="updateRefreshInterval()" style="margin-top: 5px;">
                <option value="15">15 seconds</option>
                <option value="30" selected>30 seconds</option>
                <option value="60">1 minute</option>
                <option value="120">2 minutes</option>
                <option value="300">5 minutes</option>
            </select>
        `;
        filterPanel.appendChild(refreshControls);
    }
}

// Toggle auto-refresh
function toggleAutoRefresh() {
    const checkbox = document.getElementById('auto-refresh-toggle');
    if (!checkbox) return;
    
    autoRefreshEnabled = checkbox.checked;
    
    if (autoRefreshEnabled) {
        startAutoRefresh();
    } else {
        stopAutoRefresh();
    }
}

// Update refresh interval
function updateRefreshInterval() {
    const select = document.getElementById('refresh-interval');
    if (!select) return;
    
    autoRefreshIntervalMs = parseInt(select.value) * 1000;
    
    if (autoRefreshEnabled) {
        stopAutoRefresh();
        startAutoRefresh();
    }
}

// Start auto-refresh
function startAutoRefresh() {
    stopAutoRefresh(); // Clear any existing interval
    
    autoRefreshInterval = setInterval(() => {
        console.log(`Auto-refreshing ${currentTab} tab...`);
        switch(currentTab) {
            case 'overview':
                loadOverview();
                break;
            case 'strategies':
                loadStrategies();
                break;
            case 'symbols':
                loadSymbols();
                break;
            case 'portfolio':
                loadPortfolio();
                break;
            case 'risk':
                loadRisk();
                break;
            case 'trades':
                loadTrades();
                break;
        }
    }, autoRefreshIntervalMs);
    
    console.log(`Auto-refresh enabled: ${autoRefreshIntervalMs / 1000} seconds`);
}

// Stop auto-refresh
function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
});

// Tab switching
function switchTab(tabName) {
    currentTab = tabName;
    
    // Update tab buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    
    // Update tab panes
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('active');
    });
    document.getElementById(`${tabName}-tab`).classList.add('active');
    
    // Load tab data
    switch(tabName) {
        case 'overview':
            loadOverview();
            break;
        case 'strategies':
            loadStrategies();
            break;
        case 'symbols':
            loadSymbols();
            break;
        case 'portfolio':
            loadPortfolio();
            break;
        case 'risk':
            loadRisk();
            break;
        case 'trades':
            loadTrades();
            break;
        case 'comparison':
            loadStrategyComparison();
            break;
    }
}

// Fetch Dashboard Overview
async function fetchDashboardOverview(filters) {
    const params = new URLSearchParams();
    if (filters.start_date) params.append('start_date', filters.start_date);
    if (filters.end_date) params.append('end_date', filters.end_date);
    if (filters.account_id) params.append('account_id', filters.account_id);
    
    const response = await authFetch(`/api/dashboard/overview?${params}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch overview: ${response.statusText}`);
    }
    return await response.json();
}

// Fetch Strategy Performance
async function fetchStrategyPerformance(filters) {
    const params = new URLSearchParams();
    if (filters.strategy_name) params.append('strategy_name', filters.strategy_name);
    if (filters.symbol) params.append('symbol', filters.symbol);
    if (filters.status) params.append('status', filters.status);
    if (filters.account_id) params.append('account_id', filters.account_id);
    if (filters.start_date) params.append('start_date', filters.start_date);
    if (filters.end_date) params.append('end_date', filters.end_date);
    if (filters.rank_by) params.append('rank_by', filters.rank_by);
    
    const response = await authFetch(`/api/strategies/performance?${params}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch strategy performance: ${response.statusText}`);
    }
    return await response.json();
}

// Fetch Symbol Performance
async function fetchSymbolPerformance(filters) {
    const params = new URLSearchParams();
    if (filters.account_id) params.append('account_id', filters.account_id);
    if (filters.start_date) params.append('start_date', filters.start_date);
    if (filters.end_date) params.append('end_date', filters.end_date);
    
    const response = await authFetch(`/api/trades/pnl/overview?${params}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch symbol performance: ${response.statusText}`);
    }
    return await response.json();
}

// Fetch Portfolio Analytics
async function fetchPortfolioAnalytics(filters) {
    const params = new URLSearchParams();
    if (filters.account_id) params.append('account_id', filters.account_id);
    
    const response = await authFetch(`/api/risk/metrics/portfolio?${params}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch portfolio analytics: ${response.statusText}`);
    }
    return await response.json();
}

// Fetch Risk Metrics (Real-time Risk Status)
async function fetchRiskMetrics(filters) {
    const params = new URLSearchParams();
    if (filters.account_id) params.append('account_id', filters.account_id);
    
    const response = await authFetch(`/api/risk/status/realtime?${params}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch risk metrics: ${response.statusText}`);
    }
    return await response.json();
}

// Fetch Trade Activity
async function fetchTradeActivity(filters) {
    const params = new URLSearchParams();
    if (filters.symbol) params.append('symbol', filters.symbol);
    if (filters.strategy_id) params.append('strategy_id', filters.strategy_id);
    if (filters.start_date) params.append('start_date', filters.start_date);
    if (filters.end_date) params.append('end_date', filters.end_date);
    if (filters.side) params.append('side', filters.side);
    if (filters.account_id) params.append('account_id', filters.account_id);
    
    const response = await authFetch(`/api/trades/list?${params}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch trades: ${response.statusText}`);
    }
    return await response.json();
}

// Load Overview Tab
async function loadOverview() {
    const container = document.getElementById('overview-metrics');
    container.innerHTML = '<div class="loading">Loading overview...</div>';
    
    try {
        const data = await fetchDashboardOverview(currentFilters);
        renderOverview(data);
        renderPnLTimeline(data);
    } catch (error) {
        container.innerHTML = `<div class="error">Error loading overview: ${error.message}</div>`;
        console.error('Error loading overview:', error);
    }
}

// Render Overview
function renderOverview(data) {
    const container = document.getElementById('overview-metrics');
    
    const formatCurrency = (value) => {
        if (value === null || value === undefined) return 'N/A';
        // USDT is not a valid ISO currency code, so format as number with USDT suffix
        return new Intl.NumberFormat('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(value) + ' USDT';
    };
    
    const formatPercent = (value) => {
        if (value === null || value === undefined) return 'N/A';
        return `${value.toFixed(2)}%`;
    };
    
    const cards = [
        {
            title: 'Total PnL',
            value: formatCurrency(data.total_pnl),
            change: data.pnl_change_24h !== null && data.pnl_change_24h !== undefined 
                ? `${data.pnl_change_24h >= 0 ? '+' : ''}${formatCurrency(data.pnl_change_24h)} (24h)` 
                : null,
            positive: data.total_pnl >= 0,
            additional_info: data.pnl_change_7d !== null && data.pnl_change_7d !== undefined 
                ? `7d: ${data.pnl_change_7d >= 0 ? '+' : ''}${formatCurrency(data.pnl_change_7d)} | 30d: ${data.pnl_change_30d !== null && data.pnl_change_30d !== undefined ? (data.pnl_change_30d >= 0 ? '+' : '') + formatCurrency(data.pnl_change_30d) : 'N/A'}`
                : null
        },
        {
            title: 'Realized PnL',
            value: formatCurrency(data.realized_pnl),
            positive: data.realized_pnl >= 0
        },
        {
            title: 'Unrealized PnL',
            value: formatCurrency(data.unrealized_pnl),
            positive: data.unrealized_pnl >= 0
        },
        {
            title: 'Active Strategies',
            value: data.active_strategies,
            subtitle: `of ${data.total_strategies} total`
        },
        {
            title: 'Completed Trades',
            value: data.completed_trades,
            subtitle: `${data.total_trades} total`
        },
        {
            title: 'Win Rate',
            value: formatPercent(data.overall_win_rate)
        },
        {
            title: 'Best Strategy',
            value: data.best_strategy ? data.best_strategy.strategy_name : 'N/A',
            subtitle: data.best_strategy ? formatCurrency(data.best_strategy.total_pnl) : null
        },
        {
            title: 'Top Symbol',
            value: data.top_symbol ? data.top_symbol.symbol : 'N/A',
            subtitle: data.top_symbol ? formatCurrency(data.top_symbol.total_pnl) : null
        },
        {
            title: 'Total Trade Fees',
            value: data.total_trade_fees !== null && data.total_trade_fees !== undefined ? formatCurrency(data.total_trade_fees) : 'N/A',
            subtitle: 'Trading fees paid'
        },
        {
            title: 'Total Funding Fees',
            value: data.total_funding_fees !== null && data.total_funding_fees !== undefined ? formatCurrency(data.total_funding_fees) : 'N/A',
            subtitle: 'Funding fees paid'
        }
    ];
    
    container.innerHTML = cards.map(card => `
        <div class="metric-card ${card.positive !== undefined ? (card.positive ? 'positive' : 'negative') : ''}">
            <h3>${card.title}</h3>
            <div class="value ${card.positive !== undefined ? (card.positive ? 'positive' : 'negative') : ''}">${card.value}</div>
            ${card.subtitle ? `<div class="change">${card.subtitle}</div>` : ''}
            ${card.change ? `<div class="change">${card.change}</div>` : ''}
            ${card.additional_info ? `<div class="change" style="font-size: 0.8em; color: #888; margin-top: 5px;">${card.additional_info}</div>` : ''}
        </div>
    `).join('');
}

// Render PnL Timeline Chart
let pnlChartInstance = null;

function renderPnLTimeline(data) {
    const chartContainer = document.getElementById('pnl-chart');
    
    if (!chartContainer) {
        console.warn('PnL chart container not found');
        return;
    }
    
    // Clear previous chart
    if (pnlChartInstance) {
        try {
            pnlChartInstance.remove();
        } catch (e) {
            console.warn('Error removing previous chart:', e);
        }
        pnlChartInstance = null;
    }
    
    // Check if chart library is loaded
    if (typeof LightweightCharts === 'undefined') {
        chartContainer.innerHTML = '<p style="color: #dc3545; padding: 20px; text-align: center;">Chart library not loaded. Please refresh the page.</p>';
        return;
    }
    
    // Check if we have timeline data
    if (!data || !data.pnl_timeline || !Array.isArray(data.pnl_timeline) || data.pnl_timeline.length === 0) {
        chartContainer.innerHTML = '<p style="color: #666; padding: 20px; text-align: center;">No PnL timeline data available. Complete some trades to see the chart.</p>';
        return;
    }
    
    // Validate that data.pnl_timeline contains valid objects
    const validTimelineItems = data.pnl_timeline.filter(item => 
        item && typeof item === 'object' && item.timestamp !== null && item.timestamp !== undefined && item.pnl !== null && item.pnl !== undefined
    );
    
    if (validTimelineItems.length === 0) {
        chartContainer.innerHTML = '<p style="color: #666; padding: 20px; text-align: center;">No valid timeline data points found.</p>';
        return;
    }
    
    // Use requestAnimationFrame to ensure container is ready
    requestAnimationFrame(() => {
        try {
            // Clear the container completely (remove any placeholder text)
            // But preserve dimensions
            chartContainer.innerHTML = '';
            
            // Ensure container has explicit dimensions
            if (!chartContainer.style.width) {
                chartContainer.style.width = '100%';
            }
            if (!chartContainer.style.height) {
                chartContainer.style.height = '400px';
            }
            chartContainer.style.minHeight = '400px';
            
            // Ensure container is visible (check if parent is visible)
            const parent = chartContainer.parentElement;
            if (parent) {
                const parentDisplay = window.getComputedStyle(parent).display;
                if (parentDisplay === 'none') {
                    console.warn('Chart container parent is hidden');
                }
            }
        
        // Prepare data series - TradingView expects Unix timestamp in seconds as number
        // Sort by timestamp first to ensure chronological order
        const sortedTimeline = [...data.pnl_timeline].sort((a, b) => {
            const tsA = a && a.timestamp ? (typeof a.timestamp === 'number' ? a.timestamp : parseInt(a.timestamp) || 0) : 0;
            const tsB = b && b.timestamp ? (typeof b.timestamp === 'number' ? b.timestamp : parseInt(b.timestamp) || 0) : 0;
            return tsA - tsB;
        });
        
        const chartData = sortedTimeline
            .map((point, index) => {
                // Strict validation: ensure both timestamp and pnl are valid
                if (!point) {
                    console.warn(`Timeline point ${index} is null/undefined`);
                    return null;
                }
                
                if (point.timestamp === null || point.timestamp === undefined) {
                    console.warn(`Timeline point ${index} missing timestamp:`, point);
                    return null;
                }
                
                if (point.pnl === null || point.pnl === undefined) {
                    console.warn(`Timeline point ${index} missing PnL:`, point);
                    return null;
                }
                
                // Ensure timestamp is a number (Unix seconds)
                let timestamp = point.timestamp;
                if (typeof timestamp === 'string') {
                    timestamp = parseInt(timestamp, 10);
                }
                // Handle timestamp that might be in milliseconds (convert to seconds)
                if (timestamp > 1e12) {
                    timestamp = Math.floor(timestamp / 1000);
                }
                
                // Validate timestamp
                if (typeof timestamp !== 'number' || isNaN(timestamp) || !isFinite(timestamp) || timestamp <= 0 || timestamp > 2e10) {
                    console.warn(`Timeline point ${index} invalid timestamp:`, timestamp, point);
                    return null;
                }
                
                // Ensure PnL is a valid number
                const pnlValue = typeof point.pnl === 'number' ? point.pnl : parseFloat(point.pnl);
                if (typeof pnlValue !== 'number' || isNaN(pnlValue) || !isFinite(pnlValue)) {
                    console.warn(`Timeline point ${index} invalid PnL:`, point.pnl, point);
                    return null;
                }
                
                return {
                    time: timestamp, // Unix timestamp in seconds
                    value: pnlValue
                };
            })
            .filter(point => point !== null); // Remove invalid points
        
        if (chartData.length === 0) {
            chartContainer.innerHTML = '<p style="color: #666; padding: 20px; text-align: center;">No valid timeline data points. Check that trades have exit_time values.</p>';
            return;
        }
        
        console.log(`Rendering PnL timeline with ${chartData.length} data points (from ${data.pnl_timeline.length} total)`);
        console.log('Sample data points:', chartData.slice(0, 3));
        if (chartData.length > 0) {
            console.log('First timestamp:', chartData[0].time, '=', new Date(chartData[0].time * 1000).toISOString());
            console.log('Last timestamp:', chartData[chartData.length - 1].time, '=', new Date(chartData[chartData.length - 1].time * 1000).toISOString());
        }
        
        // Ensure container has proper dimensions
        // Wait a bit if dimensions are 0 (container might not be visible yet)
        let containerWidth = chartContainer.clientWidth || chartContainer.offsetWidth;
        const containerHeight = 400;
        
        if (!containerWidth || containerWidth <= 0) {
            // Try getting width from parent or use default
            const parentWidth = chartContainer.parentElement?.clientWidth || 800;
            containerWidth = parentWidth;
            chartContainer.style.width = `${containerWidth}px`;
        }
        
        // Validate container is a valid DOM element
        if (!chartContainer || !(chartContainer instanceof HTMLElement)) {
            console.error('Chart container is not a valid DOM element');
            return;
        }
        
        // Create chart with error handling
        try {
            // Ensure all config values are non-null and valid
            // Force numeric conversion with fallbacks
            const finalWidth = Math.max(Number(containerWidth) || 800, 100);
            const finalHeight = Math.max(Number(containerHeight) || 400, 100);
            
            if (!finalWidth || !finalHeight || finalWidth <= 0 || finalHeight <= 0) {
                throw new Error(`Invalid container dimensions: width=${finalWidth}, height=${finalHeight}`);
            }
            
            // Validate LightweightCharts enums exist before using them
            if (!LightweightCharts || !LightweightCharts.CrosshairMode) {
                throw new Error('LightweightCharts.CrosshairMode is not available');
            }
            
            const crosshairMode = LightweightCharts.CrosshairMode.Normal;
            if (crosshairMode === null || crosshairMode === undefined) {
                throw new Error('LightweightCharts.CrosshairMode.Normal is null/undefined');
            }
            
            // Build config ensuring no null values anywhere
            const chartConfig = {
                width: finalWidth,
                height: finalHeight,
                layout: {
                    background: { color: '#ffffff' },
                    textColor: '#333',
                },
                grid: {
                    vertLines: { color: '#f0f0f0' },
                    horzLines: { color: '#f0f0f0' },
                },
                timeScale: {
                    timeVisible: true,
                    secondsVisible: false,
                },
                rightPriceScale: {
                    borderColor: '#d1d4dc',
                },
                crosshair: {
                    mode: crosshairMode,  // Use validated value
                },
            };
            
            // Deep validation: ensure no null/undefined anywhere in config
            const checkForNulls = (obj, path = 'config') => {
                for (const [key, value] of Object.entries(obj)) {
                    const currentPath = `${path}.${key}`;
                    if (value === null) {
                        throw new Error(`Null value found at ${currentPath}`);
                    }
                    if (value === undefined) {
                        throw new Error(`Undefined value found at ${currentPath}`);
                    }
                    if (typeof value === 'object' && !Array.isArray(value) && value !== null) {
                        checkForNulls(value, currentPath);
                    }
                }
            };
            
            try {
                checkForNulls(chartConfig);
            } catch (nullError) {
                console.error('Null/undefined in chart config:', nullError.message);
                console.error('Config object:', chartConfig);
                throw nullError;
            }
            
            // Triple-check critical values before passing to library
            if (chartConfig.width === null || chartConfig.width === undefined) {
                throw new Error(`Chart width is null/undefined: ${chartConfig.width}`);
            }
            if (chartConfig.height === null || chartConfig.height === undefined) {
                throw new Error(`Chart height is null/undefined: ${chartConfig.height}`);
            }
            if (chartContainer === null || chartContainer === undefined) {
                throw new Error(`Chart container is null/undefined: ${chartContainer}`);
            }
            
            // Final check: ensure width and height are actual numbers, not NaN or 0
            // Note: finalWidth and finalHeight are already validated above, just double-check
            if (isNaN(chartConfig.width) || chartConfig.width <= 0) {
                throw new Error(`Invalid width: ${chartConfig.width}`);
            }
            if (isNaN(chartConfig.height) || chartConfig.height <= 0) {
                throw new Error(`Invalid height: ${chartConfig.height}`);
            }
            
            // One more null check on the final config
            console.log('Creating chart with validated config:', { 
                width: chartConfig.width, 
                height: chartConfig.height,
                containerExists: !!chartContainer,
                containerType: typeof chartContainer,
                containerIsHTMLElement: chartContainer instanceof HTMLElement,
                containerWidth: chartContainer?.clientWidth
            });
            
            // Serialize and parse config to remove any hidden null/undefined values
            // This ensures we have a clean object with only valid values
            let cleanConfig;
            try {
                const configStr = JSON.stringify(chartConfig);
                if (configStr.includes('null') || configStr.includes('undefined')) {
                    console.error('Found null/undefined in serialized config:', configStr);
                    throw new Error('Config contains null/undefined values');
                }
                cleanConfig = JSON.parse(configStr);
            } catch (jsonError) {
                console.error('Error serializing config:', jsonError);
                throw new Error('Failed to validate config: ' + jsonError.message);
            }
            
            // Replace container check - ensure it's definitely not null
            if (chartContainer === null || chartContainer === undefined || !(chartContainer instanceof HTMLElement)) {
                console.error('Container validation failed:', {
                    isNull: chartContainer === null,
                    isUndefined: chartContainer === undefined,
                    isHTMLElement: chartContainer instanceof HTMLElement,
                    type: typeof chartContainer
                });
                throw new Error('Chart container is invalid');
            }
            
            // Final validation: log every property before passing to library
            console.log('Final config before createChart:', cleanConfig);
            console.log('Container element:', chartContainer);
            console.log('All config values:', Object.keys(cleanConfig).map(key => ({
                key,
                value: cleanConfig[key],
                type: typeof cleanConfig[key],
                isNull: cleanConfig[key] === null
            })));
            
            pnlChartInstance = LightweightCharts.createChart(chartContainer, cleanConfig);
            console.log('Chart created successfully');
        } catch (error) {
            console.error('Error creating chart:', error);
            console.error('Container element:', chartContainer);
            console.error('Container dimensions:', {
                clientWidth: chartContainer.clientWidth,
                offsetWidth: chartContainer.offsetWidth,
                clientHeight: chartContainer.clientHeight
            });
            chartContainer.innerHTML = `<p style="color: #dc3545; padding: 20px; text-align: center;">Error creating chart: ${error.message}. Check console for details.</p>`;
            return;
        }
        
        // Validate all data points one more time before passing to chart
        const finalChartData = chartData.filter(point => {
            const isValid = point &&
                typeof point.time === 'number' &&
                !isNaN(point.time) &&
                point.time > 0 &&
                typeof point.value === 'number' &&
                !isNaN(point.value) &&
                point.value !== null &&
                point.value !== undefined;
            
            if (!isValid) {
                console.error('Invalid data point filtered out:', point);
            }
            return isValid;
        });
        
        if (finalChartData.length === 0) {
            chartContainer.innerHTML = '<p style="color: #666; padding: 20px; text-align: center;">No valid data points after filtering. Please check console for errors.</p>';
            return;
        }
        
        console.log(`Setting chart data with ${finalChartData.length} valid points`);
        
        // Add line series with safe color determination
        // Ensure total_pnl is a valid number (default to 0 if null/undefined)
        const totalPnl = (data.total_pnl !== null && data.total_pnl !== undefined) ? data.total_pnl : 0;
        const lineColor = totalPnl >= 0 ? '#28a745' : '#dc3545';
        
        // Add line series
        const lineSeries = pnlChartInstance.addLineSeries({
            color: lineColor,
            lineWidth: 2,
            priceFormat: {
                type: 'price',
                precision: 4,
                minMove: 0.0001,
            },
            title: 'Cumulative PnL',
        });
        
        try {
            lineSeries.setData(finalChartData);
            console.log('Chart data set successfully');
        } catch (error) {
            console.error('Error setting chart data:', error);
            console.error('Data that caused error:', finalChartData);
            chartContainer.innerHTML = `<p style="color: #dc3545; padding: 20px; text-align: center;">Error rendering chart: ${error.message}. Check console for details.</p>`;
            return;
        }
        
        // Add marker series for trade points (optional visual enhancement)
        // You can add markers at each trade completion point if desired
        
        // Export chart functionality
        window.exportPnLChart = function() {
            if (!pnlChartInstance) return;
            
            // Create a data export
            const exportData = {
                title: 'Portfolio PnL Timeline',
                data: data.pnl_timeline.map(point => ({
                    timestamp: new Date(point.timestamp * 1000).toISOString(),
                    cumulative_pnl: point.pnl,
                    trade_pnl: point.trade_pnl
                })),
                exported_at: new Date().toISOString(),
                summary: {
                    total_trades: data.pnl_timeline.length,
                    final_pnl: data.pnl_timeline.length > 0 ? data.pnl_timeline[data.pnl_timeline.length - 1].pnl : 0,
                    total_realized_pnl: data.realized_pnl,
                    total_unrealized_pnl: data.unrealized_pnl
                }
            };
            
            // Download as JSON
            const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `pnl-timeline-${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        };
        
        // Add export button to chart container
        const chartHeader = chartContainer.previousElementSibling;
        if (chartHeader && chartHeader.tagName === 'H3') {
            const exportBtn = document.createElement('button');
            exportBtn.textContent = 'Export Data';
            exportBtn.className = 'btn btn-secondary';
            exportBtn.style.cssText = 'float: right; margin-top: -40px; padding: 5px 15px; font-size: 0.9em;';
            exportBtn.onclick = window.exportPnLChart;
            chartHeader.style.position = 'relative';
            chartHeader.appendChild(exportBtn);
        }
        
        // Handle window resize
        const resizeObserver = new ResizeObserver(entries => {
            if (pnlChartInstance && entries.length > 0) {
                const width = entries[0].contentRect.width;
                pnlChartInstance.applyOptions({ width });
            }
        });
        
        resizeObserver.observe(chartContainer);
        
        } catch (error) {
            console.error('Error rendering PnL timeline chart:', error);
            chartContainer.innerHTML = `<p style="color: #dc3545; padding: 20px; text-align: center;">Error rendering chart: ${error.message}</p>`;
        }
        }); // End requestAnimationFrame
}

// Load Strategies Tab
async function loadStrategies() {
    const container = document.getElementById('strategies-content');
    
    try {
        const data = await fetchStrategyPerformance(currentFilters);
        renderStrategies(data);
        renderStrategyComparisonChart(data);
    } catch (error) {
        container.innerHTML = `<div class="error">Error loading strategies: ${error.message}</div>`;
        console.error('Error loading strategies:', error);
    }
}

// Render Strategies
function renderStrategies(data) {
    const container = document.getElementById('strategies-content');
    
    if (!data.strategies || data.strategies.length === 0) {
        container.innerHTML = '<div class="empty-state">No strategies found</div>';
        return;
    }
    
    const formatCurrency = (value) => {
        if (value === null || value === undefined) return 'N/A';
        // USDT is not a valid ISO currency code, so format as number with USDT suffix
        return new Intl.NumberFormat('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(value) + ' USDT';
    };
    
    const table = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Strategy</th>
                    <th>Symbol</th>
                    <th>Status</th>
                    <th>Total PnL</th>
                    <th>Realized PnL</th>
                    <th>Unrealized PnL</th>
                    <th>Win Rate</th>
                    <th>Trades</th>
                    <th>Trade Fees</th>
                    <th>Funding Fees</th>
                </tr>
            </thead>
            <tbody>
                ${data.strategies.map(s => `
                    <tr>
                        <td>${s.rank || 'N/A'}</td>
                        <td>${s.strategy_name}</td>
                        <td>${s.symbol}</td>
                        <td><span class="badge badge-${s.status.value}">${s.status.value}</span></td>
                        <td class="${s.total_pnl >= 0 ? 'positive' : 'negative'}">${formatCurrency(s.total_pnl)}</td>
                        <td>${formatCurrency(s.total_realized_pnl)}</td>
                        <td>${formatCurrency(s.total_unrealized_pnl)}</td>
                        <td>${s.win_rate.toFixed(2)}%</td>
                        <td>${s.completed_trades} / ${s.total_trades}</td>
                        <td>${formatCurrency(s.total_trade_fees || 0)}</td>
                        <td>${formatCurrency(s.total_funding_fees || 0)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = table;
}

// Strategy comparison chart instance
let strategyComparisonChartInstance = null;

// Render Strategy Comparison Chart
function renderStrategyComparisonChart(data) {
    const container = document.getElementById('strategies-content');
    if (!container) {
        console.warn('Strategies content container not found');
        return;
    }
    
    // Check if we have strategy data
    if (!data.strategies || data.strategies.length === 0) {
        return;
    }
    
    try {
        // Create bar chart visualization
        const strategies = data.strategies.slice(0, 10); // Limit to top 10 for readability
        const maxPnL = Math.max(...strategies.map(s => Math.abs(s.total_pnl)), 0.01); // Avoid division by zero
        
        const chartHTML = `
            <div class="chart-container" style="margin-top: 30px;">
                <h3>Strategy Performance Comparison</h3>
                <div style="padding: 20px;">
                    ${strategies.map((strategy, index) => {
                        const widthPercent = Math.abs(strategy.total_pnl) / maxPnL * 100;
                        const isPositive = strategy.total_pnl >= 0;
                        
                        return `
                            <div style="margin-bottom: 15px;">
                                <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                                    <span style="font-weight: 600;">${strategy.strategy_name}</span>
                                    <span style="color: ${isPositive ? '#28a745' : '#dc3545'}; font-weight: 600;">
                                        ${isPositive ? '+' : ''}${strategy.total_pnl.toFixed(2)} USDT
                                    </span>
                                </div>
                                <div style="background: #f0f0f0; height: 30px; border-radius: 4px; overflow: hidden; position: relative;">
                                    <div style="
                                        background: ${isPositive ? '#28a745' : '#dc3545'};
                                        width: ${widthPercent}%;
                                        height: 100%;
                                        transition: width 0.3s ease;
                                        display: flex;
                                        align-items: center;
                                        padding-left: 10px;
                                        color: white;
                                        font-weight: 600;
                                        font-size: 0.9em;
                                    ">${strategy.completed_trades} trades</div>
                                </div>
                                <div style="display: flex; justify-content: space-between; margin-top: 5px; font-size: 0.85em; color: #666;">
                                    <span>Win Rate: ${strategy.win_rate.toFixed(2)}%</span>
                                    <span>Symbol: ${strategy.symbol}</span>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
        
        container.innerHTML += chartHTML;
        
    } catch (error) {
        console.error('Error rendering strategy comparison chart:', error);
    }
}

// Load Symbols Tab
async function loadSymbols() {
    const container = document.getElementById('symbols-content');
    
    try {
        const data = await fetchSymbolPerformance(currentFilters);
        renderSymbols(data);
    } catch (error) {
        container.innerHTML = `<div class="error">Error loading symbols: ${error.message}</div>`;
        console.error('Error loading symbols:', error);
    }
}

// Render Symbols
function renderSymbols(data) {
    const container = document.getElementById('symbols-content');
    
    if (!data || data.length === 0) {
        container.innerHTML = '<div class="empty-state">No symbol data found</div>';
        return;
    }
    
    // Sort by total PnL
    const sorted = [...data].sort((a, b) => b.total_pnl - a.total_pnl);
    
    const formatCurrency = (value) => {
        if (value === null || value === undefined) return 'N/A';
        // USDT is not a valid ISO currency code, so format as number with USDT suffix
        return new Intl.NumberFormat('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(value) + ' USDT';
    };
    
    const table = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Total PnL</th>
                    <th>Realized PnL</th>
                    <th>Unrealized PnL</th>
                    <th>Win Rate</th>
                    <th>Completed Trades</th>
                    <th>Total Trades</th>
                    <th>Open Positions</th>
                    <th>Trade Fees</th>
                    <th>Funding Fees</th>
                </tr>
            </thead>
            <tbody>
                ${sorted.map(s => `
                    <tr>
                        <td><strong>${s.symbol}</strong></td>
                        <td class="${s.total_pnl >= 0 ? 'positive' : 'negative'}">${formatCurrency(s.total_pnl)}</td>
                        <td>${formatCurrency(s.total_realized_pnl)}</td>
                        <td>${formatCurrency(s.total_unrealized_pnl)}</td>
                        <td>${s.win_rate.toFixed(2)}%</td>
                        <td>${s.completed_trades}</td>
                        <td>${s.total_trades}</td>
                        <td>${s.open_positions ? s.open_positions.length : 0}</td>
                        <td>${formatCurrency(s.total_trade_fees || 0)}</td>
                        <td>${formatCurrency(s.total_funding_fees || 0)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = table;
}

// Load Portfolio Tab
async function loadPortfolio() {
    const container = document.getElementById('portfolio-content');
    
    try {
        const data = await fetchPortfolioAnalytics(currentFilters);
        renderPortfolio(data);
    } catch (error) {
        container.innerHTML = `<div class="error">Error loading portfolio: ${error.message}</div>`;
        console.error('Error loading portfolio:', error);
    }
}

// Render Portfolio
function renderPortfolio(data) {
    const container = document.getElementById('portfolio-content');
    
    if (!data || !data.metrics) {
        container.innerHTML = '<div class="empty-state">No portfolio data available</div>';
        return;
    }
    
    const metrics = data.metrics;
    const accountId = data.account_id || 'all';
    
    // Format currency
    const formatCurrency = (value) => {
        if (value === null || value === undefined) return 'N/A';
        return new Intl.NumberFormat('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(value) + ' USDT';
    };
    
    // Format percentage
    const formatPercent = (value) => {
        if (value === null || value === undefined) return 'N/A';
        return value.toFixed(2) + '%';
    };
    
    // Calculate return percentage
    const returnPct = metrics.initial_balance > 0 
        ? ((metrics.current_balance - metrics.initial_balance) / metrics.initial_balance) * 100 
        : 0;
    
    // Portfolio Overview Metrics
    const overviewHTML = `
        <div class="overview-grid" style="margin-bottom: 30px;">
            <div class="metric-card ${returnPct >= 0 ? 'positive' : 'negative'}">
                <h3>Current Balance</h3>
                <div class="value ${returnPct >= 0 ? 'positive' : 'negative'}">${formatCurrency(metrics.current_balance)}</div>
                <div class="change">From ${formatCurrency(metrics.initial_balance)}</div>
            </div>
            <div class="metric-card ${returnPct >= 0 ? 'positive' : 'negative'}">
                <h3>Total Return</h3>
                <div class="value ${returnPct >= 0 ? 'positive' : 'negative'}">${formatCurrency(metrics.current_balance - metrics.initial_balance)}</div>
                <div class="change">${returnPct >= 0 ? '+' : ''}${formatPercent(returnPct)}</div>
            </div>
            <div class="metric-card ${metrics.total_pnl >= 0 ? 'positive' : 'negative'}">
                <h3>Total PnL</h3>
                <div class="value ${metrics.total_pnl >= 0 ? 'positive' : 'negative'}">${formatCurrency(metrics.total_pnl)}</div>
                <div class="change">From ${metrics.total_trades} trades</div>
            </div>
            <div class="metric-card">
                <h3>Peak Balance</h3>
                <div class="value">${formatCurrency(metrics.peak_balance)}</div>
                <div class="change">Highest balance reached</div>
            </div>
        </div>
    `;
    
    // Performance Metrics
    const performanceHTML = `
        <div class="chart-container">
            <h3>Performance Metrics</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">
                <div class="metric-card">
                    <h3>Win Rate</h3>
                    <div class="value">${formatPercent(metrics.win_rate)}</div>
                    <div class="change">${metrics.winning_trades}W / ${metrics.losing_trades}L</div>
                </div>
                <div class="metric-card ${metrics.profit_factor >= 1 ? 'positive' : 'negative'}">
                    <h3>Profit Factor</h3>
                    <div class="value">${metrics.profit_factor ? metrics.profit_factor.toFixed(2) : 'N/A'}</div>
                    <div class="change">${formatCurrency(metrics.gross_profit)} / ${formatCurrency(Math.abs(metrics.gross_loss))}</div>
                </div>
                <div class="metric-card">
                    <h3>Avg Win</h3>
                    <div class="value positive">${formatCurrency(metrics.avg_win)}</div>
                    <div class="change">Per winning trade</div>
                </div>
                <div class="metric-card">
                    <h3>Avg Loss</h3>
                    <div class="value negative">${formatCurrency(metrics.avg_loss)}</div>
                    <div class="change">Per losing trade</div>
                </div>
                <div class="metric-card">
                    <h3>Sharpe Ratio</h3>
                    <div class="value">${metrics.sharpe_ratio !== null && metrics.sharpe_ratio !== undefined ? metrics.sharpe_ratio.toFixed(2) : 'N/A'}</div>
                    <div class="change">Risk-adjusted returns</div>
                </div>
            </div>
        </div>
    `;
    
    // Risk Metrics
    const riskHTML = `
        <div class="chart-container">
            <h3>Risk Metrics</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">
                <div class="metric-card ${metrics.current_drawdown_pct <= 10 ? 'positive' : metrics.current_drawdown_pct <= 20 ? '' : 'negative'}">
                    <h3>Current Drawdown</h3>
                    <div class="value ${metrics.current_drawdown_pct <= 10 ? 'positive' : metrics.current_drawdown_pct <= 20 ? '' : 'negative'}">${formatPercent(metrics.current_drawdown_pct)}</div>
                    <div class="change">${formatCurrency(metrics.current_drawdown_usdt)}</div>
                </div>
                <div class="metric-card">
                    <h3>Max Drawdown</h3>
                    <div class="value negative">${formatPercent(metrics.max_drawdown_pct)}</div>
                    <div class="change">${formatCurrency(metrics.max_drawdown_usdt)}</div>
                </div>
                <div class="metric-card">
                    <h3>Total Trades</h3>
                    <div class="value">${metrics.total_trades}</div>
                    <div class="change">Completed: ${metrics.winning_trades + metrics.losing_trades}</div>
                </div>
            </div>
        </div>
    `;
    
    container.innerHTML = `
        <div style="margin-bottom: 20px;">
            <h2>Portfolio Analytics - Account: ${accountId === 'all' ? 'All Accounts' : accountId}</h2>
            <p style="color: #666; font-size: 0.9em;">Calculated at: ${data.calculated_at ? new Date(data.calculated_at).toLocaleString() : 'N/A'}</p>
        </div>
        ${overviewHTML}
        ${performanceHTML}
        ${riskHTML}
    `;
}

// Load Risk Tab
async function loadRisk() {
    const container = document.getElementById('risk-content');
    
    try {
        const data = await fetchRiskMetrics(currentFilters);
        renderRisk(data);
    } catch (error) {
        container.innerHTML = `<div class="error">Error loading risk metrics: ${error.message}</div>`;
        console.error('Error loading risk metrics:', error);
    }
}

// Render Risk
function renderRisk(data) {
    const container = document.getElementById('risk-content');
    
    if (!data) {
        container.innerHTML = '<div class="empty-state">No risk data available</div>';
        return;
    }
    
    // Format currency
    const formatCurrency = (value) => {
        if (value === null || value === undefined) return 'N/A';
        return new Intl.NumberFormat('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(value) + ' USDT';
    };
    
    // Format percentage
    const formatPercent = (value) => {
        if (value === null || value === undefined) return 'N/A';
        return value.toFixed(2) + '%';
    };
    
    // Get risk status color
    const getStatusColor = (status) => {
        switch(status) {
            case 'normal': return '#28a745';
            case 'warning': return '#ffc107';
            case 'breach': return '#dc3545';
            case 'paused': return '#6c757d';
            default: return '#6c757d';
        }
    };
    
    const riskStatus = data.risk_status || 'normal';
    const accountId = data.account_id || 'all';
    const timestamp = data.timestamp ? new Date(data.timestamp).toLocaleString() : 'N/A';
    
    // Risk Status Badge
    const statusBadge = `
        <div style="background: ${getStatusColor(riskStatus)}; color: white; padding: 15px; border-radius: 8px; margin-bottom: 25px; text-align: center;">
            <h2 style="margin: 0; color: white;">Risk Status: ${riskStatus.toUpperCase()}</h2>
            <p style="margin: 5px 0 0 0; opacity: 0.9;">Account: ${accountId === 'all' ? 'All Accounts' : accountId} | Updated: ${timestamp}</p>
        </div>
    `;
    
    // Exposure Metrics
    const exposure = data.current_exposure || {};
    const exposureHTML = `
        <div class="chart-container">
            <h3>Portfolio Exposure</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">
                <div class="metric-card ${exposure.status === 'breach' ? 'negative' : 'positive'}">
                    <h3>Total Exposure</h3>
                    <div class="value">${formatCurrency(exposure.total_exposure_usdt)}</div>
                    <div class="change">${formatPercent(exposure.total_exposure_pct || 0)} of balance</div>
                    ${exposure.limit_usdt ? `<div class="change" style="margin-top: 5px;">Limit: ${formatCurrency(exposure.limit_usdt)}</div>` : ''}
                </div>
            </div>
        </div>
    `;
    
    // Loss Limits
    const lossLimits = data.loss_limits || {};
    const dailyLoss = lossLimits.daily_loss_usdt || 0;
    const weeklyLoss = lossLimits.weekly_loss_usdt || 0;
    const dailyLossPct = lossLimits.daily_loss_pct || 0;
    const weeklyLossPct = lossLimits.weekly_loss_pct || 0;
    
    const lossLimitsHTML = `
        <div class="chart-container">
            <h3>Loss Limits</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">
                <div class="metric-card ${dailyLoss < 0 && lossLimits.daily_loss_limit_usdt && Math.abs(dailyLoss) >= (lossLimits.daily_loss_limit_usdt * 0.8) ? (Math.abs(dailyLoss) >= lossLimits.daily_loss_limit_usdt ? 'negative' : '') : 'positive'}">
                    <h3>Daily PnL</h3>
                    <div class="value ${dailyLoss >= 0 ? 'positive' : 'negative'}">${formatCurrency(dailyLoss)}</div>
                    <div class="change">${formatPercent(dailyLossPct)}</div>
                    ${lossLimits.daily_loss_limit_usdt ? `<div class="change" style="margin-top: 5px;">Limit: ${formatCurrency(lossLimits.daily_loss_limit_usdt)}</div>` : ''}
                </div>
                <div class="metric-card ${weeklyLoss < 0 && lossLimits.weekly_loss_limit_usdt && Math.abs(weeklyLoss) >= (lossLimits.weekly_loss_limit_usdt * 0.8) ? (Math.abs(weeklyLoss) >= lossLimits.weekly_loss_limit_usdt ? 'negative' : '') : 'positive'}">
                    <h3>Weekly PnL</h3>
                    <div class="value ${weeklyLoss >= 0 ? 'positive' : 'negative'}">${formatCurrency(weeklyLoss)}</div>
                    <div class="change">${formatPercent(weeklyLossPct)}</div>
                    ${lossLimits.weekly_loss_limit_usdt ? `<div class="change" style="margin-top: 5px;">Limit: ${formatCurrency(lossLimits.weekly_loss_limit_usdt)}</div>` : ''}
                </div>
            </div>
        </div>
    `;
    
    // Drawdown
    const drawdown = data.drawdown || {};
    const drawdownPct = drawdown.current_drawdown_pct || 0;
    const maxDrawdown = drawdown.max_drawdown_pct || null;
    
    const drawdownHTML = `
        <div class="chart-container">
            <h3>Drawdown</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">
                <div class="metric-card ${drawdown.status === 'breach' ? 'negative' : drawdownPct <= 10 ? 'positive' : drawdownPct <= 20 ? '' : 'negative'}">
                    <h3>Current Drawdown</h3>
                    <div class="value ${drawdownPct <= 10 ? 'positive' : drawdownPct <= 20 ? '' : 'negative'}">${formatPercent(drawdownPct)}</div>
                    ${maxDrawdown ? `<div class="change">Max Limit: ${formatPercent(maxDrawdown)}</div>` : ''}
                </div>
            </div>
        </div>
    `;
    
    // Circuit Breakers
    const circuitBreakers = data.circuit_breakers || {};
    const circuitBreakersHTML = `
        <div class="chart-container">
            <h3>Circuit Breakers</h3>
            <div style="padding: 20px;">
                <p><strong>Status:</strong> ${circuitBreakers.active ? '<span style="color: #dc3545;">ACTIVE</span>' : '<span style="color: #28a745;">Inactive</span>'}</p>
                ${circuitBreakers.breakers && circuitBreakers.breakers.length > 0 ? `
                    <ul>
                        ${circuitBreakers.breakers.map(b => `<li>${b}</li>`).join('')}
                    </ul>
                ` : '<p>No active circuit breakers</p>'}
            </div>
        </div>
    `;
    
    // Recent Enforcement Events
    const events = data.recent_enforcement_events || [];
    const eventsHTML = events.length > 0 ? `
        <div class="chart-container">
            <h3>Recent Enforcement Events</h3>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Type</th>
                        <th>Message</th>
                    </tr>
                </thead>
                <tbody>
                    ${events.slice(0, 10).map(event => `
                        <tr>
                            <td>${event.created_at ? new Date(event.created_at).toLocaleString() : 'N/A'}</td>
                            <td><span style="color: #dc3545; font-weight: 600;">${event.event_type || 'N/A'}</span></td>
                            <td>${event.message || 'N/A'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    ` : `
        <div class="chart-container">
            <h3>Recent Enforcement Events</h3>
            <p>No recent enforcement events</p>
        </div>
    `;
    
    container.innerHTML = `
        ${statusBadge}
        ${exposureHTML}
        ${lossLimitsHTML}
        ${drawdownHTML}
        ${circuitBreakersHTML}
        ${eventsHTML}
    `;
}

// Load Trades Tab
async function loadTrades() {
    const container = document.getElementById('trades-content');
    
    try {
        const data = await fetchTradeActivity(currentFilters);
        renderTrades(data);
    } catch (error) {
        container.innerHTML = `<div class="error">Error loading trades: ${error.message}</div>`;
        console.error('Error loading trades:', error);
    }
}

// Render Trades
function renderTrades(data) {
    const container = document.getElementById('trades-content');
    
    if (!data || data.length === 0) {
        container.innerHTML = '<div class="empty-state">No trades found</div>';
        return;
    }
    
    // Limit to 100 most recent trades
    const recent = data.slice(0, 100);
    
    const formatDate = (dateStr) => {
        if (!dateStr) return 'N/A';
        return new Date(dateStr).toLocaleString();
    };
    
    const table = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Strategy</th>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Price</th>
                    <th>Quantity</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                ${recent.map(t => `
                    <tr>
                        <td>${formatDate(t.timestamp)}</td>
                        <td>${t.strategy_name || t.strategy_id || 'N/A'}</td>
                        <td>${t.symbol}</td>
                        <td>${t.side}</td>
                        <td>${t.price}</td>
                        <td>${t.executed_qty}</td>
                        <td>${t.status}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    container.innerHTML = table;
}

// Load Accounts for Filter
async function loadAccounts() {
    try {
        const response = await authFetch('/api/accounts/list');
        if (response.ok) {
            const accounts = await response.json();
            const select = document.getElementById('account-filter');
            accounts.forEach(account => {
                const option = document.createElement('option');
                option.value = account.account_id;
                option.textContent = account.name || account.account_id;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading accounts:', error);
    }
}

// Apply Filters
function applyFilters() {
    const startDate = document.getElementById('date-range-start').value;
    const endDate = document.getElementById('date-range-end').value;
    const accountId = document.getElementById('account-filter').value;
    
    currentFilters = {
        start_date: startDate || null,
        end_date: endDate || null,
        account_id: accountId || null
    };
    
    // Reload current tab
    switchTab(currentTab);
}

// Reset Filters
function resetFilters() {
    document.getElementById('date-range-start').value = '';
    document.getElementById('date-range-end').value = '';
    document.getElementById('account-filter').value = '';
    
    currentFilters = {
        start_date: null,
        end_date: null,
        account_id: null
    };
    
    // Reload current tab
    switchTab(currentTab);
}

// ============================================================================
// Strategy Comparison Functions
// ============================================================================

let comparisonData = null;
let currentSortColumn = null;
let currentSortDirection = 'asc';

// Load Strategy Comparison Tab
async function loadStrategyComparison() {
    console.log('loadStrategyComparison() called');
    
    const select = document.getElementById('strategy-select');
    if (!select) {
        console.error('Strategy select element not found in DOM. Looking for #strategy-select');
        return;
    }
    
    console.log('Strategy select element found, loading strategies...');
    
    // Show loading state
    select.innerHTML = '<option value="" disabled>Loading strategies...</option>';
    
    try {
        console.log('Fetching from /api/strategies/performance');
        // Load available strategies
        const response = await authFetch('/api/strategies/performance');
        console.log('Response status:', response.status, response.statusText);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Failed to load strategies:', response.status, errorText);
            throw new Error(`Failed to load strategies: ${response.status} ${errorText}`);
        }
        
        const contentType = response.headers.get('content-type') || '';
        console.log('Response content-type:', contentType);
        
        if (!contentType.includes('application/json')) {
            const text = await response.text();
            console.error('Non-JSON response:', text.substring(0, 200));
            throw new Error(`Expected JSON but received ${contentType}`);
        }
        
        const data = await response.json();
        console.log('Strategies data received:', data);
        console.log('Data keys:', Object.keys(data));
        console.log('data.strategies:', data.strategies);
        
        // Handle different response structures
        const strategies = data.strategies || data || [];
        console.log('Strategies to populate:', strategies.length, strategies);
        
        if (!Array.isArray(strategies)) {
            console.error('Invalid strategies data format:', strategies, typeof strategies);
            throw new Error('Invalid response format: strategies is not an array');
        }
        
        if (strategies.length === 0) {
            console.warn('No strategies found in response');
            select.innerHTML = '<option value="" disabled>No strategies available</option>';
            return;
        }
        
        console.log('Calling populateStrategySelector with', strategies.length, 'strategies');
        populateStrategySelector(strategies);
        
        // Set up event listeners (only once)
        const compareBtn = document.getElementById('compare-btn');
        const clearBtn = document.getElementById('clear-comparison-btn');
        const viewMode = document.getElementById('view-mode');
        
        if (compareBtn && !compareBtn.hasAttribute('data-listener-attached')) {
            compareBtn.addEventListener('click', runComparison);
            compareBtn.setAttribute('data-listener-attached', 'true');
        }
        
        if (clearBtn && !clearBtn.hasAttribute('data-listener-attached')) {
            clearBtn.addEventListener('click', clearComparison);
            clearBtn.setAttribute('data-listener-attached', 'true');
        }
        
        if (viewMode && !viewMode.hasAttribute('data-listener-attached')) {
            viewMode.addEventListener('change', (e) => switchComparisonView(e.target.value));
            viewMode.setAttribute('data-listener-attached', 'true');
        }
    } catch (error) {
        console.error('Error loading strategies:', error);
        const resultsDiv = document.getElementById('comparison-results');
        if (resultsDiv) {
            resultsDiv.innerHTML = `<div class="error">Failed to load strategies for comparison: ${error.message}</div>`;
        }
        // Also show error in the selector itself
        const select = document.getElementById('strategy-select');
        if (select) {
            select.innerHTML = '';
            const option = document.createElement('option');
            option.value = '';
            option.textContent = `Error: ${error.message}`;
            option.disabled = true;
            select.appendChild(option);
        }
    }
}

// Populate Strategy Selector
function populateStrategySelector(strategies) {
    console.log('populateStrategySelector() called with', strategies);
    
    const select = document.getElementById('strategy-select');
    if (!select) {
        console.error('Strategy select element not found in populateStrategySelector');
        return;
    }
    
    if (!Array.isArray(strategies)) {
        console.error('populateStrategySelector: strategies is not an array', strategies, typeof strategies);
        select.innerHTML = '<option value="" disabled>Error: Invalid data format</option>';
        return;
    }
    
    select.innerHTML = ''; // Clear existing options
    
    if (strategies.length === 0) {
        console.warn('No strategies to populate');
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No strategies available';
        option.disabled = true;
        select.appendChild(option);
        return;
    }
    
    console.log('Populating', strategies.length, 'strategies');
    let populatedCount = 0;
    
    strategies.forEach((strategy, index) => {
        try {
            console.log(`Strategy ${index}:`, strategy);
            const option = document.createElement('option');
            option.value = strategy.strategy_id || strategy.id || `strategy_${index}`;
            const name = strategy.strategy_name || strategy.name || 'Unknown';
            const symbol = strategy.symbol || '';
            const type = strategy.strategy_type || strategy.type || '';
            option.textContent = `${name} (${symbol}) - ${type}`;
            select.appendChild(option);
            populatedCount++;
        } catch (error) {
            console.error(`Error adding strategy ${index}:`, error, strategy);
        }
    });
    
    console.log(`Successfully populated ${populatedCount} out of ${strategies.length} strategies in selector`);
    
    if (populatedCount === 0) {
        select.innerHTML = '<option value="" disabled>Error: Could not populate strategies</option>';
    }
}

// Run Comparison
async function runComparison() {
    const select = document.getElementById('strategy-select');
    if (!select) return;
    
    const selectedIds = Array.from(select.selectedOptions)
        .map(opt => opt.value);
    
    if (selectedIds.length < 1) {
        const resultsDiv = document.getElementById('comparison-results');
        if (resultsDiv) {
            resultsDiv.innerHTML = '<div class="error">Please select at least one strategy to compare</div>';
        }
        return;
    }
    
    if (selectedIds.length > 10) {
        const resultsDiv = document.getElementById('comparison-results');
        if (resultsDiv) {
            resultsDiv.innerHTML = '<div class="error">Maximum 10 strategies can be compared at once</div>';
        }
        return;
    }
    
    const startDate = document.getElementById('comparison-start-date')?.value || '';
    const endDate = document.getElementById('comparison-end-date')?.value || '';
    
    try {
        const params = new URLSearchParams({
            strategy_ids: selectedIds.join(',')
        });
        if (startDate) params.append('start_date', startDate);
        if (endDate) params.append('end_date', endDate);
        
        const resultsDiv = document.getElementById('comparison-results');
        if (resultsDiv) {
            resultsDiv.innerHTML = '<div class="loading">Comparing strategies...</div>';
        }
        
        const response = await authFetch(`/api/dashboard/strategy-comparison?${params}`);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Failed to compare strategies' }));
            throw new Error(errorData.detail || 'Failed to compare strategies');
        }
        
        const data = await response.json();
        comparisonData = data;
        
        const viewMode = document.getElementById('view-mode')?.value || 'table';
        switchComparisonView(viewMode, data);
    } catch (error) {
        console.error('Error running comparison:', error);
        const resultsDiv = document.getElementById('comparison-results');
        if (resultsDiv) {
            resultsDiv.innerHTML = `<div class="error">Failed to compare strategies: ${error.message}</div>`;
        }
    }
}

// Switch Comparison View
function switchComparisonView(mode, data = null) {
    const dataToUse = data || comparisonData;
    if (!dataToUse) {
        return;
    }
    
    // Hide all views
    document.querySelectorAll('.comparison-view').forEach(view => {
        view.style.display = 'none';
    });
    
    switch(mode) {
        case 'table':
            renderComparisonTable(dataToUse);
            break;
        case 'cards':
            renderComparisonCards(dataToUse);
            break;
        case 'chart':
            renderComparisonCharts(dataToUse);
            break;
        case 'params':
            renderParameterComparison(dataToUse);
            break;
    }
}

// Render Comparison Table
function renderComparisonTable(data) {
    const resultsDiv = document.getElementById('comparison-results');
    if (!resultsDiv) return;
    
    if (!data.strategies || data.strategies.length === 0) {
        resultsDiv.innerHTML = '<div class="empty-state">No strategies to compare</div>';
        return;
    }
    
    // Add summary statistics
    const totalPnL = data.strategies.reduce((sum, s) => sum + parseFloat(s.total_pnl || 0), 0);
    const totalTrades = data.strategies.reduce((sum, s) => sum + (s.completed_trades || 0), 0);
    const totalWins = data.strategies.reduce((sum, s) => sum + (s.winning_trades || 0), 0);
    const totalLosses = data.strategies.reduce((sum, s) => sum + (s.losing_trades || 0), 0);
    const totalTradeFees = data.strategies.reduce((sum, s) => sum + parseFloat(s.total_trade_fees || 0), 0);
    const totalFundingFees = data.strategies.reduce((sum, s) => sum + parseFloat(s.total_funding_fees || 0), 0);
    const avgWinRate = data.strategies.length > 0 
        ? data.strategies.reduce((sum, s) => sum + parseFloat(s.win_rate || 0), 0) / data.strategies.length 
        : 0;
    
    let html = '<div id="comparison-table-view" class="comparison-view">';
    
    // Summary Section
    html += '<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">';
    html += `<div><div style="font-size: 0.9em; opacity: 0.9;">Total PnL</div><div style="font-size: 1.8em; font-weight: bold;">$${totalPnL.toFixed(2)}</div></div>`;
    html += `<div><div style="font-size: 0.9em; opacity: 0.9;">Total Trades</div><div style="font-size: 1.8em; font-weight: bold;">${totalTrades}</div></div>`;
    html += `<div><div style="font-size: 0.9em; opacity: 0.9;">Win Rate</div><div style="font-size: 1.8em; font-weight: bold;">${avgWinRate.toFixed(1)}%</div></div>`;
    html += `<div><div style="font-size: 0.9em; opacity: 0.9;">Wins / Losses</div><div style="font-size: 1.8em; font-weight: bold;">${totalWins} / ${totalLosses}</div></div>`;
    html += `<div><div style="font-size: 0.9em; opacity: 0.9;">Total Fees</div><div style="font-size: 1.8em; font-weight: bold;">$${(totalTradeFees + totalFundingFees).toFixed(2)}</div></div>`;
    html += `<div style="display: flex; align-items: center; gap: 10px;"><button onclick="exportComparisonData()" style="padding: 10px 20px; background: rgba(255,255,255,0.2); border: 1px solid rgba(255,255,255,0.3); color: white; border-radius: 4px; cursor: pointer; font-weight: 600;">📥 Export</button></div>`;
    html += '</div>';
    
    // Get all metrics to display
    const metrics = [
        { key: 'strategy_name', label: 'Strategy Name', format: 'text' },
        { key: 'symbol', label: 'Symbol', format: 'text' },
        { key: 'strategy_type', label: 'Type', format: 'text' },
        { key: 'total_pnl', label: 'Total PnL', format: 'currency' },
        { key: 'total_realized_pnl', label: 'Realized PnL', format: 'currency' },
        { key: 'total_unrealized_pnl', label: 'Unrealized PnL', format: 'currency' },
        { key: 'win_rate', label: 'Win Rate', format: 'percent' },
        { key: 'completed_trades', label: 'Trades', format: 'number' },
        { key: 'winning_trades', label: 'Wins', format: 'number' },
        { key: 'losing_trades', label: 'Losses', format: 'number' },
        { key: 'avg_profit_per_trade', label: 'Avg Profit/Trade', format: 'currency' },
        { key: 'largest_win', label: 'Highest Win', format: 'currency' },
        { key: 'largest_loss', label: 'Highest Loss', format: 'currency' },
        { key: 'total_trade_fees', label: 'Trade Fees', format: 'currency' },
        { key: 'total_funding_fees', label: 'Funding Fees', format: 'currency' },
        { key: 'total_running_time_seconds', label: 'Running Time', format: 'duration' },
        { key: 'leverage', label: 'Leverage', format: 'number' },
        { key: 'risk_per_trade', label: 'Risk %', format: 'percent' }
    ];
    
    // Build table
    html += '<table id="comparison-table" class="data-table" style="width: 100%;">';
    html += '<thead><tr>';
    
    metrics.forEach(metric => {
        html += `<th onclick="sortComparisonTable('${metric.key}')" title="Click to sort" style="cursor: pointer;">${metric.label} <span class="sort-indicator"></span></th>`;
    });
    
    html += '</tr></thead><tbody>';
    
    data.strategies.forEach(strategy => {
        html += '<tr>';
        metrics.forEach(metric => {
            let value = strategy[metric.key];
            let cellClass = '';
            
            // Format value
            if (value === null || value === undefined) {
                value = 'N/A';
            } else if (metric.format === 'currency') {
                value = `$${parseFloat(value).toFixed(2)}`;
            } else if (metric.format === 'percent') {
                value = `${parseFloat(value).toFixed(2)}%`;
            } else if (metric.format === 'number') {
                value = parseFloat(value).toFixed(2);
            } else if (metric.format === 'duration') {
                value = formatDuration(parseFloat(value));
            } else if (metric.format === 'text') {
                value = String(value);
            }
            
            // Highlight best/worst if comparison metrics available
            // Map metric keys to comparison_metrics field names
            if (data.comparison_metrics) {
                const metricKey = metric.key;
                let metricData = null;
                
                // Map frontend metric keys to backend comparison_metrics fields
                const metricMapping = {
                    'total_pnl': null,  // Calculate on-the-fly
                    'win_rate': null,   // Calculate on-the-fly
                    'completed_trades': null,  // Calculate on-the-fly
                    'total_trade_fees': 'fee_impact',
                    'total_funding_fees': 'fee_impact',
                    'total_running_time_seconds': 'uptime_percent',
                };
                
                // Check if this metric has a direct mapping
                if (metricMapping[metricKey] && data.comparison_metrics[metricMapping[metricKey]]) {
                    metricData = data.comparison_metrics[metricMapping[metricKey]];
                } else {
                    // For metrics not in comparison_metrics, calculate best/worst on-the-fly
                    // Only do this for numeric metrics
                    if (metric.format === 'currency' || metric.format === 'percent' || metric.format === 'number') {
                        const values = data.strategies.map(s => {
                            const v = s[metricKey];
                            return v !== null && v !== undefined ? parseFloat(v) : (metricKey.includes('pnl') ? -Infinity : Infinity);
                        }).filter(v => isFinite(v));
                        
                        if (values.length > 0) {
                            const maxVal = Math.max(...values);
                            const minVal = Math.min(...values);
                            const currentVal = strategy[metricKey] !== null && strategy[metricKey] !== undefined 
                                ? parseFloat(strategy[metricKey]) : null;
                            
                            // For PnL and positive metrics: higher is better
                            // For fees and negative metrics: lower is better
                            const isPositiveMetric = metricKey.includes('pnl') || metricKey.includes('win_rate') || 
                                                     metricKey.includes('trades') || metricKey.includes('running_time');
                            
                            if (currentVal !== null && isFinite(currentVal)) {
                                if (isPositiveMetric && currentVal === maxVal && maxVal !== minVal) {
                                    cellClass = 'value-best';
                                } else if (!isPositiveMetric && currentVal === minVal && maxVal !== minVal) {
                                    cellClass = 'value-best';
                                } else if (isPositiveMetric && currentVal === minVal && maxVal !== minVal) {
                                    cellClass = 'value-worst';
                                } else if (!isPositiveMetric && currentVal === maxVal && maxVal !== minVal) {
                                    cellClass = 'value-worst';
                                }
                            }
                        }
                    }
                }
                
                // Use comparison_metrics if available
                if (metricData) {
                    if (metricData.best_strategy_id === strategy.strategy_id) {
                        cellClass = 'value-best';
                    } else if (metricData.worst_strategy_id === strategy.strategy_id) {
                        cellClass = 'value-worst';
                    }
                }
            }
            
            html += `<td class="${cellClass}">${value}</td>`;
        });
        html += '</tr>';
    });
    
    html += '</tbody></table>';
    html += '</div>';
    
    resultsDiv.innerHTML = html;
    
    // Update sort indicator
    updateSortIndicator();
}

// Sort Comparison Table
function sortComparisonTable(column) {
    if (!comparisonData || !comparisonData.strategies) return;
    
    const direction = (currentSortColumn === column && currentSortDirection === 'asc') ? 'desc' : 'asc';
    currentSortColumn = column;
    currentSortDirection = direction;
    
    comparisonData.strategies.sort((a, b) => {
        let aVal = a[column];
        let bVal = b[column];
        
        if (aVal === null || aVal === undefined) aVal = -Infinity;
        if (bVal === null || bVal === undefined) bVal = -Infinity;
        
        if (direction === 'asc') {
            return aVal > bVal ? 1 : (aVal < bVal ? -1 : 0);
        } else {
            return aVal < bVal ? 1 : (aVal > bVal ? -1 : 0);
        }
    });
    
    renderComparisonTable(comparisonData);
}

// Update Sort Indicator
function updateSortIndicator() {
    if (!currentSortColumn) return;
    
    document.querySelectorAll('.sort-indicator').forEach(ind => {
        ind.textContent = '';
    });
    
    const headers = document.querySelectorAll('#comparison-table th');
    headers.forEach((header, index) => {
        const onclick = header.getAttribute('onclick');
        if (onclick && onclick.includes(`'${currentSortColumn}'`)) {
            const indicator = header.querySelector('.sort-indicator');
            if (indicator) {
                indicator.textContent = currentSortDirection === 'asc' ? ' ↑' : ' ↓';
            }
        }
    });
}

// Render Comparison Cards
function renderComparisonCards(data) {
    const resultsDiv = document.getElementById('comparison-results');
    if (!resultsDiv) return;
    
    if (!data.strategies || data.strategies.length === 0) {
        resultsDiv.innerHTML = '<div class="empty-state">No strategies to compare</div>';
        return;
    }
    
    let html = '<div id="comparison-cards-view" class="comparison-view">';
    html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-top: 20px;">';
    
    data.strategies.forEach(strategy => {
        const pnlColor = strategy.total_pnl >= 0 ? '#28a745' : '#dc3545';
        const pnlIcon = strategy.total_pnl >= 0 ? '📈' : '📉';
        const winRateColor = strategy.win_rate >= 50 ? '#28a745' : strategy.win_rate >= 30 ? '#ffc107' : '#dc3545';
        
        html += `<div class="comparison-card" style="background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1); border-left: 4px solid ${pnlColor};">`;
        
        // Header
        html += `<div style="border-bottom: 1px solid #e9ecef; padding-bottom: 15px; margin-bottom: 15px;">`;
        html += `<h3 style="margin: 0 0 5px 0; color: #333;">${strategy.strategy_name}</h3>`;
        html += `<div style="color: #666; font-size: 0.9em;">${strategy.symbol} • ${strategy.strategy_type}</div>`;
        html += `</div>`;
        
        // Key Metrics Grid
        html += `<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px;">`;
        
        // Total PnL
        html += `<div>`;
        html += `<div style="color: #666; font-size: 0.85em; margin-bottom: 5px;">Total PnL</div>`;
        html += `<div style="font-size: 1.5em; font-weight: bold; color: ${pnlColor};">${pnlIcon} $${parseFloat(strategy.total_pnl).toFixed(2)}</div>`;
        html += `</div>`;
        
        // Win Rate
        html += `<div>`;
        html += `<div style="color: #666; font-size: 0.85em; margin-bottom: 5px;">Win Rate</div>`;
        html += `<div style="font-size: 1.5em; font-weight: bold; color: ${winRateColor};">${parseFloat(strategy.win_rate).toFixed(1)}%</div>`;
        html += `</div>`;
        
        // Realized PnL
        html += `<div>`;
        html += `<div style="color: #666; font-size: 0.85em; margin-bottom: 5px;">Realized PnL</div>`;
        html += `<div style="font-size: 1.2em; font-weight: 600; color: ${strategy.total_realized_pnl >= 0 ? '#28a745' : '#dc3545'};">$${parseFloat(strategy.total_realized_pnl).toFixed(2)}</div>`;
        html += `</div>`;
        
        // Completed Trades
        html += `<div>`;
        html += `<div style="color: #666; font-size: 0.85em; margin-bottom: 5px;">Trades</div>`;
        html += `<div style="font-size: 1.2em; font-weight: 600;">${strategy.completed_trades}</div>`;
        html += `</div>`;
        
        html += `</div>`;
        
        // Trade Breakdown
        html += `<div style="background: #f8f9fa; border-radius: 4px; padding: 12px; margin-bottom: 15px;">`;
        html += `<div style="display: flex; justify-content: space-between; font-size: 0.9em;">`;
        html += `<span style="color: #28a745;">✅ Wins: <strong>${strategy.winning_trades}</strong></span>`;
        html += `<span style="color: #dc3545;">❌ Losses: <strong>${strategy.losing_trades}</strong></span>`;
        html += `</div>`;
        html += `</div>`;
        
        // Additional Metrics
        html += `<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.9em; color: #666;">`;
        html += `<div>Avg Profit/Trade: <strong style="color: #333;">$${parseFloat(strategy.avg_profit_per_trade || 0).toFixed(2)}</strong></div>`;
        html += `<div>Leverage: <strong style="color: #333;">${strategy.leverage}x</strong></div>`;
        html += `<div>Risk/Trade: <strong style="color: #333;">${parseFloat(strategy.risk_per_trade || 0).toFixed(2)}%</strong></div>`;
        if (strategy.total_unrealized_pnl !== null && strategy.total_unrealized_pnl !== undefined) {
            html += `<div>Unrealized: <strong style="color: ${strategy.total_unrealized_pnl >= 0 ? '#28a745' : '#dc3545'};">$${parseFloat(strategy.total_unrealized_pnl).toFixed(2)}</strong></div>`;
        }
        html += `</div>`;
        
        // Highest Win/Loss Section
        if ((strategy.largest_win !== null && strategy.largest_win !== undefined && strategy.largest_win > 0) ||
            (strategy.largest_loss !== null && strategy.largest_loss !== undefined && strategy.largest_loss < 0)) {
            html += `<div style="background: #f8f9fa; border-radius: 4px; padding: 12px; margin-top: 15px; border-top: 1px solid #e9ecef;">`;
            html += `<div style="display: flex; justify-content: space-between; font-size: 0.9em;">`;
            if (strategy.largest_win !== null && strategy.largest_win !== undefined && strategy.largest_win > 0) {
                html += `<span>🏆 Highest Win: <strong style="color: #28a745;">$${parseFloat(strategy.largest_win).toFixed(2)}</strong></span>`;
            }
            if (strategy.largest_loss !== null && strategy.largest_loss !== undefined && strategy.largest_loss < 0) {
                html += `<span>📉 Highest Loss: <strong style="color: #dc3545;">$${parseFloat(Math.abs(strategy.largest_loss)).toFixed(2)}</strong></span>`;
            }
            html += `</div>`;
            html += `</div>`;
        }
        
        // Fees Section
        if (strategy.total_trade_fees !== null && strategy.total_trade_fees !== undefined) {
            html += `<div style="background: #f8f9fa; border-radius: 4px; padding: 12px; margin-top: 15px; border-top: 1px solid #e9ecef;">`;
            html += `<div style="display: flex; justify-content: space-between; font-size: 0.9em;">`;
            html += `<span>💰 Trade Fees: <strong>$${parseFloat(strategy.total_trade_fees).toFixed(2)}</strong></span>`;
            if (strategy.total_funding_fees !== null && strategy.total_funding_fees !== undefined) {
                html += `<span>💸 Funding Fees: <strong>$${parseFloat(strategy.total_funding_fees).toFixed(2)}</strong></span>`;
            }
            html += `</div>`;
            // Calculate fee impact
            if (strategy.total_pnl !== null && strategy.total_pnl !== 0) {
                const totalFees = (strategy.total_trade_fees || 0) + (strategy.total_funding_fees || 0);
                const feeImpact = (totalFees / Math.abs(strategy.total_pnl)) * 100;
                html += `<div style="margin-top: 8px; font-size: 0.85em; color: #666;">Fee Impact: <strong>${feeImpact.toFixed(2)}%</strong> of PnL</div>`;
            }
            html += `</div>`;
        }
        
        // Running Time Section
        if (strategy.total_running_time_seconds !== null && strategy.total_running_time_seconds !== undefined) {
            html += `<div style="background: #e8f4f8; border-radius: 4px; padding: 12px; margin-top: 15px; border-top: 1px solid #e9ecef;">`;
            html += `<div style="font-size: 0.9em;">`;
            html += `<span>⏱️ Total Running Time: <strong>${formatDuration(strategy.total_running_time_seconds)}</strong></span>`;
            html += `</div>`;
            html += `</div>`;
        }
        
        // Status Badge
        const statusColors = {
            'running': '#28a745',
            'stopped': '#6c757d',
            'error': '#dc3545'
        };
        const statusEmojis = {
            'running': '🟢',
            'stopped': '🔴',
            'error': '❌'
        };
        const status = strategy.status?.value || strategy.status || 'stopped';
        html += `<div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e9ecef;">`;
        html += `<span style="background: ${statusColors[status] || '#6c757d'}; color: white; padding: 4px 12px; border-radius: 12px; font-size: 0.85em; font-weight: 600;">${statusEmojis[status] || '⚪'} ${status.toUpperCase()}</span>`;
        html += `</div>`;
        
        html += `</div>`;
    });
    
    html += '</div>';
    html += '</div>';
    
    resultsDiv.innerHTML = html;
}

// Render Comparison Charts
function renderComparisonCharts(data) {
    const resultsDiv = document.getElementById('comparison-results');
    if (!resultsDiv) return;
    
    if (!data.strategies || data.strategies.length === 0) {
        resultsDiv.innerHTML = '<div class="empty-state">No strategies to compare</div>';
        return;
    }
    
    let html = '<div id="comparison-charts-view" class="comparison-view">';
    
    // PnL Comparison Chart
    html += '<div class="chart-container" style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1); margin-bottom: 20px;">';
    html += '<h3 style="margin-top: 0;">Total PnL Comparison</h3>';
    html += '<canvas id="pnl-comparison-chart" style="max-height: 400px;"></canvas>';
    html += '</div>';
    
    // Win Rate Comparison Chart
    html += '<div class="chart-container" style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1); margin-bottom: 20px;">';
    html += '<h3 style="margin-top: 0;">Win Rate Comparison</h3>';
    html += '<canvas id="winrate-comparison-chart" style="max-height: 400px;"></canvas>';
    html += '</div>';
    
    // Trades Comparison Chart
    html += '<div class="chart-container" style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1); margin-bottom: 20px;">';
    html += '<h3 style="margin-top: 0;">Trades Count Comparison</h3>';
    html += '<canvas id="trades-comparison-chart" style="max-height: 400px;"></canvas>';
    html += '</div>';
    
    // Performance Metrics Radar Chart
    html += '<div class="chart-container" style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);">';
    html += '<h3 style="margin-top: 0;">Performance Metrics Comparison</h3>';
    html += '<canvas id="metrics-comparison-chart" style="max-height: 400px;"></canvas>';
    html += '</div>';
    
    html += '</div>';
    
    resultsDiv.innerHTML = html;
    
    // Render charts using Chart.js (if available) or create simple bar charts
    setTimeout(() => {
        renderComparisonChartsData(data);
    }, 100);
}

// Render Chart Data
function renderComparisonChartsData(data) {
    // Check if Chart.js is available
    if (typeof Chart === 'undefined') {
        // Fallback: Create simple HTML bar charts
        renderSimpleBarCharts(data);
        return;
    }
    
    const strategies = data.strategies || [];
    if (strategies.length === 0) {
        console.warn('No strategies data for charts');
        return;
    }
    const strategyNames = strategies.map(s => s.strategy_name || 'Unknown');
    const colors = [
        'rgba(102, 126, 234, 0.8)',
        'rgba(118, 75, 162, 0.8)',
        'rgba(40, 167, 69, 0.8)',
        'rgba(255, 193, 7, 0.8)',
        'rgba(220, 53, 69, 0.8)',
        'rgba(23, 162, 184, 0.8)',
        'rgba(108, 117, 125, 0.8)',
        'rgba(255, 87, 34, 0.8)',
        'rgba(156, 39, 176, 0.8)',
        'rgba(0, 150, 136, 0.8)'
    ];
    
    // PnL Comparison Bar Chart
    const pnlCtx = document.getElementById('pnl-comparison-chart');
    if (pnlCtx) {
        try {
            new Chart(pnlCtx, {
            type: 'bar',
            data: {
                labels: strategyNames,
                datasets: [{
                    label: 'Total PnL ($)',
                    data: strategies.map(s => parseFloat(s.total_pnl || 0)),
                    backgroundColor: strategies.map((s, i) => 
                        parseFloat(s.total_pnl || 0) >= 0 ? colors[i % colors.length] : 'rgba(220, 53, 69, 0.8)'
                    ),
                    borderColor: strategies.map((s, i) => 
                        parseFloat(s.total_pnl || 0) >= 0 ? 'rgba(102, 126, 234, 1)' : 'rgba(220, 53, 69, 1)'
                    ),
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toFixed(2);
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return 'Total PnL: $' + context.parsed.y.toFixed(2);
                            }
                        }
                    }
                }
            }
        });
        } catch (error) {
            console.error('Error rendering PnL chart:', error);
            renderSimpleBarCharts(data);
        }
    }
    
    // Win Rate Comparison Bar Chart
    const winrateCtx = document.getElementById('winrate-comparison-chart');
    if (winrateCtx) {
        try {
            new Chart(winrateCtx, {
            type: 'bar',
            data: {
                labels: strategyNames,
                datasets: [{
                    label: 'Win Rate (%)',
                    data: strategies.map(s => parseFloat(s.win_rate || 0)),
                    backgroundColor: strategies.map((s, i) => {
                        const wr = parseFloat(s.win_rate);
                        if (wr >= 50) return 'rgba(40, 167, 69, 0.8)';
                        if (wr >= 30) return 'rgba(255, 193, 7, 0.8)';
                        return 'rgba(220, 53, 69, 0.8)';
                    }),
                    borderColor: strategies.map((s, i) => colors[i % colors.length]),
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return 'Win Rate: ' + context.parsed.y.toFixed(2) + '%';
                            }
                        }
                    }
                }
            }
        });
        } catch (error) {
            console.error('Error rendering Win Rate chart:', error);
        }
    }
    
    // Trades Count Comparison Bar Chart
    const tradesCtx = document.getElementById('trades-comparison-chart');
    if (tradesCtx) {
        try {
            new Chart(tradesCtx, {
            type: 'bar',
            data: {
                labels: strategyNames,
                datasets: [{
                    label: 'Completed Trades',
                    data: strategies.map(s => s.completed_trades || 0),
                    backgroundColor: colors.slice(0, strategies.length),
                    borderColor: colors.slice(0, strategies.length).map(c => c.replace('0.8', '1')),
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return 'Trades: ' + context.parsed.y;
                            }
                        }
                    }
                }
            }
        });
        } catch (error) {
            console.error('Error rendering Trades chart:', error);
        }
    }
    
    // Performance Metrics Comparison (Multiple metrics)
    const metricsCtx = document.getElementById('metrics-comparison-chart');
    if (metricsCtx) {
        try {
            // Normalize metrics for comparison (0-100 scale)
            const maxPnL = Math.max(...strategies.map(s => Math.abs(parseFloat(s.total_pnl || 0))), 1);
            const maxTrades = Math.max(...strategies.map(s => s.completed_trades || 0), 1);
            const maxAvgProfit = Math.max(...strategies.map(s => Math.abs(parseFloat(s.avg_profit_per_trade || 0))), 1);
            
            new Chart(metricsCtx, {
            type: 'radar',
            data: {
                labels: ['PnL Score', 'Win Rate', 'Trades Volume', 'Avg Profit'],
                datasets: strategies.map((s, i) => ({
                    label: s.strategy_name,
                    data: [
                        (Math.abs(parseFloat(s.total_pnl)) / maxPnL) * 100,
                        parseFloat(s.win_rate),
                        (s.completed_trades / maxTrades) * 100,
                        (Math.abs(parseFloat(s.avg_profit_per_trade)) / maxAvgProfit) * 100
                    ],
                    backgroundColor: colors[i % colors.length].replace('0.8', '0.2'),
                    borderColor: colors[i % colors.length],
                    borderWidth: 2,
                    pointBackgroundColor: colors[i % colors.length],
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: colors[i % colors.length]
                }))
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                scales: {
                    r: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            stepSize: 20
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'bottom'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.dataset.label || '';
                                const value = context.parsed.r.toFixed(1);
                                return label + ': ' + value;
                            }
                        }
                    }
                }
            }
        });
        } catch (error) {
            console.error('Error rendering Metrics chart:', error);
        }
    }
}

// Fallback: Simple HTML Bar Charts
function renderSimpleBarCharts(data) {
    const strategies = data.strategies;
    
    // PnL Chart
    const pnlChart = document.getElementById('pnl-comparison-chart');
    if (pnlChart && pnlChart.parentElement) {
        let html = '<div style="display: flex; align-items: flex-end; height: 300px; gap: 10px; padding: 20px;">';
        const pnlValues = strategies.map(s => Math.abs(parseFloat(s.total_pnl || 0)));
        const maxPnL = Math.max(...pnlValues, 1);
        strategies.forEach(s => {
            const pnl = parseFloat(s.total_pnl || 0);
            const height = maxPnL > 0 ? (Math.abs(pnl) / maxPnL) * 100 : 0;
            const color = pnl >= 0 ? '#28a745' : '#dc3545';
            const name = s.strategy_name || 'Unknown';
            html += `<div style="flex: 1; display: flex; flex-direction: column; align-items: center;">`;
            html += `<div style="background: ${color}; width: 100%; height: ${height}%; min-height: 20px; border-radius: 4px 4px 0 0; position: relative;">`;
            html += `<div style="position: absolute; top: -25px; left: 50%; transform: translateX(-50%); white-space: nowrap; font-size: 0.85em; font-weight: 600;">$${pnl.toFixed(2)}</div>`;
            html += `</div>`;
            html += `<div style="margin-top: 10px; font-size: 0.8em; text-align: center; color: #666; writing-mode: vertical-rl; text-orientation: mixed;">${name}</div>`;
            html += `</div>`;
        });
        html += '</div>';
        pnlChart.parentElement.innerHTML = '<h3 style="margin-top: 0;">Total PnL Comparison</h3>' + html;
    }
    
    // Similar for other charts...
    const winrateChart = document.getElementById('winrate-comparison-chart');
    if (winrateChart && winrateChart.parentElement) {
        let html = '<div style="display: flex; align-items: flex-end; height: 300px; gap: 10px; padding: 20px;">';
        strategies.forEach(s => {
            const height = Math.min(Math.max(parseFloat(s.win_rate || 0), 0), 100); // Clamp between 0-100
            const color = height >= 50 ? '#28a745' : height >= 30 ? '#ffc107' : '#dc3545';
            const name = s.strategy_name || 'Unknown';
            html += `<div style="flex: 1; display: flex; flex-direction: column; align-items: center;">`;
            html += `<div style="background: ${color}; width: 100%; height: ${height}%; min-height: 20px; border-radius: 4px 4px 0 0; position: relative;">`;
            html += `<div style="position: absolute; top: -25px; left: 50%; transform: translateX(-50%); white-space: nowrap; font-size: 0.85em; font-weight: 600;">${height.toFixed(1)}%</div>`;
            html += `</div>`;
            html += `<div style="margin-top: 10px; font-size: 0.8em; text-align: center; color: #666; writing-mode: vertical-rl; text-orientation: mixed;">${name}</div>`;
            html += `</div>`;
        });
        html += '</div>';
        winrateChart.parentElement.innerHTML = '<h3 style="margin-top: 0;">Win Rate Comparison</h3>' + html;
    }
}

// Render Parameter Comparison
function renderParameterComparison(data) {
    const resultsDiv = document.getElementById('comparison-results');
    if (!resultsDiv) return;
    
    if (!data.strategies || data.strategies.length === 0) {
        resultsDiv.innerHTML = '<div class="empty-state">No strategies to compare</div>';
        return;
    }
    
    // Get all unique parameters
    const allParams = new Set();
    data.strategies.forEach(s => {
        if (s.params) {
            Object.keys(s.params).forEach(key => allParams.add(key));
        }
    });
    
    // Build parameter comparison table
    let html = '<div id="comparison-params-view" class="comparison-view">';
    html += '<table id="params-comparison-table" class="data-table" style="width: 100%;">';
    html += '<thead><tr><th>Parameter</th>';
    data.strategies.forEach(s => {
        html += `<th>${s.strategy_name}</th>`;
    });
    html += '</tr></thead><tbody>';
    
    // Group parameters
    const paramGroups = {
        'Basic': ['strategy_type', 'symbol', 'leverage', 'risk_per_trade', 'fixed_amount'],
        'EMA': ['ema_fast', 'ema_slow', 'min_ema_separation'],
        'Risk': ['take_profit_pct', 'stop_loss_pct', 'trailing_stop_enabled', 'trailing_stop_activation_pct'],
        'Trading': ['kline_interval', 'enable_short', 'enable_htf_bias', 'cooldown_candles', 'enable_ema_cross_exit'],
        'Other': Array.from(allParams).filter(p => !['strategy_type', 'symbol', 'leverage', 'risk_per_trade', 'fixed_amount', 
            'ema_fast', 'ema_slow', 'min_ema_separation', 'take_profit_pct', 'stop_loss_pct', 
            'trailing_stop_enabled', 'trailing_stop_activation_pct', 'kline_interval', 'enable_short', 
            'enable_htf_bias', 'cooldown_candles', 'enable_ema_cross_exit'].includes(p))
    };
    
    Object.entries(paramGroups).forEach(([groupName, params]) => {
        if (params.length === 0) return;
        
        html += `<tr><td colspan="${data.strategies.length + 1}" style="background: #f8f9fa; font-weight: bold;">${groupName}</td></tr>`;
        
        params.forEach(param => {
            if (!allParams.has(param)) return;
            
            html += `<tr>`;
            html += `<td><strong>${param.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</strong></td>`;
            
            const values = data.strategies.map(s => s.params?.[param] ?? 'N/A');
            const uniqueValues = new Set(values.filter(v => v !== 'N/A'));
            const isDifferent = uniqueValues.size > 1;
            
            values.forEach((value, idx) => {
                let displayValue = value;
                if (typeof value === 'boolean') {
                    displayValue = value ? 'Yes' : 'No';
                } else if (typeof value === 'number') {
                    displayValue = value.toFixed(4);
                }
                
                const cellClass = isDifferent ? 'param-different' : '';
                html += `<td class="${cellClass}">${displayValue}</td>`;
            });
            
            html += `</tr>`;
        });
    });
    
    html += '</tbody></table>';
    html += '</div>';
    
    resultsDiv.innerHTML = html;
}

// Clear Comparison
function clearComparison() {
    const select = document.getElementById('strategy-select');
    const startDate = document.getElementById('comparison-start-date');
    const endDate = document.getElementById('comparison-end-date');
    const resultsDiv = document.getElementById('comparison-results');
    
    if (select) {
        Array.from(select.options).forEach(opt => opt.selected = false);
    }
    if (startDate) startDate.value = '';
    if (endDate) endDate.value = '';
    if (resultsDiv) {
        resultsDiv.innerHTML = '<div class="empty-state">Select strategies and click "Compare" to see comparison</div>';
    }
    comparisonData = null;
}

// Export Comparison Data
function exportComparisonData() {
    if (!comparisonData || !comparisonData.strategies) {
        alert('No comparison data to export');
        return;
    }
    
    // Convert to CSV
    const strategies = comparisonData.strategies;
    const headers = [
        'Strategy Name', 'Symbol', 'Type', 'Total PnL', 'Realized PnL', 
        'Unrealized PnL', 'Win Rate', 'Completed Trades', 'Winning Trades', 
        'Losing Trades', 'Avg Profit/Trade', 'Highest Win', 'Highest Loss',
        'Trade Fees', 'Funding Fees', 'Running Time', 'Leverage', 'Risk %'
    ];
    
    let csv = headers.join(',') + '\n';
    
    strategies.forEach(s => {
        const row = [
            `"${(s.strategy_name || 'Unknown').replace(/"/g, '""')}"`, // Escape quotes in CSV
            s.symbol || 'N/A',
            s.strategy_type || 'N/A',
            s.total_pnl !== null && s.total_pnl !== undefined ? s.total_pnl : 0,
            s.total_realized_pnl !== null && s.total_realized_pnl !== undefined ? s.total_realized_pnl : 0,
            s.total_unrealized_pnl !== null && s.total_unrealized_pnl !== undefined ? s.total_unrealized_pnl : 0,
            s.win_rate !== null && s.win_rate !== undefined ? s.win_rate : 0,
            s.completed_trades || 0,
            s.winning_trades || 0,
            s.losing_trades || 0,
            s.avg_profit_per_trade !== null && s.avg_profit_per_trade !== undefined ? s.avg_profit_per_trade : 0,
            s.largest_win !== null && s.largest_win !== undefined ? s.largest_win : 0,
            s.largest_loss !== null && s.largest_loss !== undefined ? s.largest_loss : 0,
            s.total_trade_fees !== null && s.total_trade_fees !== undefined ? s.total_trade_fees : 0,
            s.total_funding_fees !== null && s.total_funding_fees !== undefined ? s.total_funding_fees : 0,
            s.total_running_time_seconds !== null && s.total_running_time_seconds !== undefined ? `"${formatDuration(s.total_running_time_seconds)}"` : 'N/A',
            s.leverage || 0,
            s.risk_per_trade !== null && s.risk_per_trade !== undefined ? s.risk_per_trade : 0
        ];
        csv += row.join(',') + '\n';
    });
    
    // Create download link
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `strategy-comparison-${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

