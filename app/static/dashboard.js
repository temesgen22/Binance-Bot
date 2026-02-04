// Dashboard JavaScript

// Check authentication
(function() {
    if (!requireAuth()) {
        throw new Error('Not authenticated');
    }
})();

const API_BASE = '';
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
            // Small delay to ensure DOM is ready
            setTimeout(() => {
                loadStrategyComparison();
            }, 100);
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
        // Try to find it with a delay (in case DOM isn't ready)
        setTimeout(() => {
            const retrySelect = document.getElementById('strategy-select');
            if (retrySelect) {
                console.log('Found strategy-select on retry');
                loadStrategyComparison();
            } else {
                console.error('Strategy select element still not found after retry');
            }
        }, 100);
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
    ];
    
    // Add additional metrics if available in comparison_metrics
    if (data.comparison_metrics) {
        if (data.comparison_metrics.profit_factor) {
            metrics.push({ key: 'profit_factor', label: 'Profit Factor', format: 'number' });
        }
        if (data.comparison_metrics.risk_reward) {
            metrics.push({ key: 'risk_reward', label: 'Risk/Reward', format: 'number' });
        }
        if (data.comparison_metrics.trades_per_day) {
            metrics.push({ key: 'trades_per_day', label: 'Trades/Day', format: 'number' });
        }
    }
    
    metrics.push(
        { key: 'leverage', label: 'Leverage', format: 'number' },
        { key: 'risk_per_trade', label: 'Risk %', format: 'percent' }
    );
    
    // Build table
    let html = '<div id="comparison-table-view" class="comparison-view">';
    html += '<table id="comparison-table" class="comparison-table">';
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
            } else if (metric.format === 'text') {
                value = String(value);
            }
            
            // Highlight best/worst if comparison metrics available
            if (data.comparison_metrics && data.comparison_metrics[metric.key]) {
                const metricData = data.comparison_metrics[metric.key];
                if (metricData.best_strategy_id === strategy.strategy_id) {
                    cellClass = 'value-best';
                } else if (metricData.worst_strategy_id === strategy.strategy_id) {
                    cellClass = 'value-worst';
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
    const metrics = [
        'strategy_name', 'symbol', 'strategy_type', 'total_pnl', 'total_realized_pnl',
        'total_unrealized_pnl', 'win_rate', 'completed_trades', 'winning_trades',
        'losing_trades', 'avg_profit_per_trade', 'profit_factor', 'risk_reward',
        'trades_per_day', 'leverage', 'risk_per_trade'
    ];
    
    headers.forEach((header, index) => {
        if (index < metrics.length && metrics[index] === currentSortColumn) {
            const indicator = header.querySelector('.sort-indicator');
            if (indicator) {
                indicator.textContent = currentSortDirection === 'asc' ? ' ↑' : ' ↓';
            }
        }
    });
}

// Render Comparison Cards (Placeholder - Phase 3)
function renderComparisonCards(data) {
    const resultsDiv = document.getElementById('comparison-results');
    if (!resultsDiv) return;
    
    resultsDiv.innerHTML = '<div class="empty-state">Cards view coming in Phase 3</div>';
}

// Render Comparison Charts (Placeholder - Phase 3)
function renderComparisonCharts(data) {
    const resultsDiv = document.getElementById('comparison-results');
    if (!resultsDiv) return;
    
    resultsDiv.innerHTML = '<div class="empty-state">Charts view coming in Phase 3</div>';
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
    html += '<table id="params-comparison-table" class="params-table">';
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
    
    if (select) select.selectedIndex = -1;
    if (startDate) startDate.value = '';
    if (endDate) endDate.value = '';
    if (resultsDiv) {
        resultsDiv.innerHTML = '<div class="empty-state">Select strategies and click "Compare" to see comparison</div>';
    }
    comparisonData = null;
}

