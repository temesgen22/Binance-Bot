/**
 * Shared Chart Utilities for TradingView Lightweight Charts
 * Used by both backtesting.html and reports.html to eliminate code duplication
 */

class ChartRenderer {
    constructor(options = {}) {
        this.defaultHeight = options.defaultHeight || 500;
        this.secondsVisible = options.secondsVisible || false;
        this.supportRangeMeanReversion = options.supportRangeMeanReversion || false;
    }
    
    /**
     * Create a TradingView Lightweight Chart instance
     */
    createChart(container, height = null) {
        if (typeof LightweightCharts === 'undefined') {
            throw new Error('TradingView Lightweight Charts library not loaded');
        }
        
        // Note: Lightweight Charts doesn't support custom timezone formatting via localization API
        // Timezone adjustment is handled in processKlineData() and createTradeMarkers() by adjusting timestamps
        return LightweightCharts.createChart(container, {
            width: container.clientWidth,
            height: height || this.defaultHeight,
            layout: {
                background: { color: '#ffffff' },
                textColor: '#333',
            },
            grid: {
                vertLines: { color: '#e0e0e0' },
                horzLines: { color: '#e0e0e0' },
            },
            timeScale: {
                timeVisible: true,
                secondsVisible: this.secondsVisible,
            },
            rightPriceScale: {
                borderColor: '#cccccc',
                scaleMargins: {
                    top: 0.1,
                    bottom: 0.1,
                },
            },
        });
    }
    
    /**
     * Create a candlestick series with standard styling
     */
    createCandlestickSeries(chart) {
        return chart.addCandlestickSeries({
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
            priceFormat: {
                type: 'price',
                precision: 6,
                minMove: 0.000001,
            },
        });
    }
    
    /**
     * Process klines data from Binance format to chart format
     * Input: Array of [timestamp_ms, open, high, low, close, volume, ...]
     * Output: Array of {time, open, high, low, close}
     * 
     * Note: If user wants UTC display, we adjust timestamps so chart's local-time display shows UTC
     */
    processKlineData(klines) {
        if (!klines || !Array.isArray(klines)) {
            return [];
        }
        
        // Get user's timezone preference
        const useUTC = typeof UserSettings !== 'undefined' && UserSettings.get('timeFormat') === 'utc';
        
        // Calculate timezone offset in seconds (if UTC is requested)
        // We need to adjust timestamps so that when chart displays them in local time, they appear as UTC
        let timezoneOffsetSeconds = 0;
        if (useUTC) {
            // Get browser's timezone offset in minutes, convert to seconds
            // Offset is negative for timezones ahead of UTC (e.g., UTC+5 = -300 minutes)
            // We ADD the offset to timestamps so local display shows UTC
            timezoneOffsetSeconds = new Date().getTimezoneOffset() * 60; // Convert minutes to seconds
        }
        
        return klines
            .filter(k => k && Array.isArray(k) && k.length >= 5 && k[0] && k[1] && k[2] && k[3] && k[4])
            .map(k => {
                const timestampMs = parseInt(k[0]);
                if (isNaN(timestampMs) || timestampMs <= 0) {
                    console.warn('Invalid kline timestamp:', k[0]);
                    return null;
                }
                
                const open = parseFloat(k[1]);
                const high = parseFloat(k[2]);
                const low = parseFloat(k[3]);
                const close = parseFloat(k[4]);
                
                if (isNaN(open) || isNaN(high) || isNaN(low) || isNaN(close)) {
                    console.warn('Invalid kline price data:', k);
                    return null;
                }
                
                // TradingView Lightweight Charts expects Unix timestamp in seconds
                // If UTC is requested, adjust timestamp so chart's local display shows UTC
                const baseTimestamp = Math.floor(timestampMs / 1000);
                const adjustedTimestamp = useUTC ? baseTimestamp + timezoneOffsetSeconds : baseTimestamp;
                
                return {
                    time: adjustedTimestamp,
                    open: open,
                    high: high,
                    low: low,
                    close: close,
                };
            })
            .filter(item => item !== null);
    }
    
    /**
     * Add EMA indicator lines to chart
     * Returns {emaFast, emaSlow} series objects or null if indicators not available
     */
    addEMALines(chart, indicators) {
        if (!indicators || !indicators.ema_fast || !indicators.ema_slow) {
            return null;
        }
        
        try {
            // EMA Fast line (blue)
            const emaFastSeries = chart.addLineSeries({
                color: '#2196F3',
                lineWidth: 2,
                title: `EMA Fast (${indicators.ema_fast_period || 8})`,
                priceLineVisible: false,
                lastValueVisible: true,
                priceFormat: {
                    type: 'price',
                    precision: 6,
                    minMove: 0.000001,
                },
            });
            
            // EMA Slow line (orange)
            const emaSlowSeries = chart.addLineSeries({
                color: '#FF9800',
                lineWidth: 2,
                title: `EMA Slow (${indicators.ema_slow_period || 21})`,
                priceLineVisible: false,
                lastValueVisible: true,
                priceFormat: {
                    type: 'price',
                    precision: 6,
                    minMove: 0.000001,
                },
            });
            
            // Set EMA data
            emaFastSeries.setData(indicators.ema_fast);
            emaSlowSeries.setData(indicators.ema_slow);
            
            return { emaFast: emaFastSeries, emaSlow: emaSlowSeries };
        } catch (e) {
            console.warn('Error adding EMA lines:', e);
            return null;
        }
    }
    
    /**
     * Setup OHLC crosshair display
     * Updates OHLC info box when user hovers over chart
     */
    setupOHLCDisplay(chart, candlestickSeries, candlestickData, indicators, ohlcConfig) {
        const {
            ohlcBoxId,
            openId,
            highId,
            lowId,
            closeId,
            changeId,
            emaFastItemId,
            emaFastId,
            emaFastLabelId,
            emaSlowItemId,
            emaSlowId,
            emaSlowLabelId,
        } = ohlcConfig;
        
        chart.subscribeCrosshairMove(param => {
            const ohlcBox = document.getElementById(ohlcBoxId);
            if (!ohlcBox) return;
            
            if (param.point === undefined || !param.time || param.seriesData.size === 0) {
                return;
            }
            
            const data = param.seriesData.get(candlestickSeries);
            if (!data || !data.time) {
                return;
            }
            
            // Find the candle data for this timestamp
            const candleTime = data.time;
            const candle = candlestickData.find(c => c.time === candleTime);
            
            if (!candle) {
                return;
            }
            
            const { open, high, low, close } = candle;
            
            // Calculate change percentage
            const change = close - open;
            const changePercent = open !== 0 ? ((change / open) * 100) : 0;
            const changeColor = change >= 0 ? '#4caf50' : '#f44336';
            const changeSign = change >= 0 ? '+' : '';
            
            // Format prices with 5 decimals
            const formatPrice = (price) => parseFloat(price).toFixed(5);
            
            // Get EMA values for this candle if available
            let emaFast = null;
            let emaSlow = null;
            let emaFastPeriod = null;
            let emaSlowPeriod = null;
            
            if (indicators && indicators.ema_fast && indicators.ema_slow) {
                const emaFastData = indicators.ema_fast.find(e => e.time === candleTime);
                const emaSlowData = indicators.ema_slow.find(e => e.time === candleTime);
                
                if (emaFastData && emaFastData.value !== undefined) {
                    emaFast = emaFastData.value;
                }
                if (emaSlowData && emaSlowData.value !== undefined) {
                    emaSlow = emaSlowData.value;
                }
                
                emaFastPeriod = indicators.ema_fast_period || 8;
                emaSlowPeriod = indicators.ema_slow_period || 21;
            }
            
            // Update OHLC display elements
            const openEl = document.getElementById(openId);
            const highEl = document.getElementById(highId);
            const lowEl = document.getElementById(lowId);
            const closeEl = document.getElementById(closeId);
            const changeEl = document.getElementById(changeId);
            
            if (openEl) openEl.textContent = formatPrice(open);
            if (highEl) highEl.textContent = formatPrice(high);
            if (lowEl) lowEl.textContent = formatPrice(low);
            if (closeEl) {
                closeEl.textContent = formatPrice(close);
                closeEl.style.color = changeColor;
            }
            if (changeEl) {
                changeEl.textContent = `${changeSign}${changePercent.toFixed(2)}%`;
                changeEl.style.color = changeColor;
            }
            
            // Update EMA values if available
            if (emaFastItemId && emaFastId && emaFastLabelId) {
                const emaFastItem = document.getElementById(emaFastItemId);
                const emaFastEl = document.getElementById(emaFastId);
                const emaFastLabel = document.getElementById(emaFastLabelId);
                
                if (emaFast !== null && emaFastItem && emaFastEl && emaFastLabel) {
                    emaFastItem.style.display = 'flex';
                    emaFastEl.textContent = formatPrice(emaFast);
                    emaFastLabel.textContent = `EMA(${emaFastPeriod})`;
                } else if (emaFastItem) {
                    emaFastItem.style.display = 'none';
                }
            }
            
            if (emaSlowItemId && emaSlowId && emaSlowLabelId) {
                const emaSlowItem = document.getElementById(emaSlowItemId);
                const emaSlowEl = document.getElementById(emaSlowId);
                const emaSlowLabel = document.getElementById(emaSlowLabelId);
                
                if (emaSlow !== null && emaSlowItem && emaSlowEl && emaSlowLabel) {
                    emaSlowItem.style.display = 'flex';
                    emaSlowEl.textContent = formatPrice(emaSlow);
                    emaSlowLabel.textContent = `EMA(${emaSlowPeriod})`;
                } else if (emaSlowItem) {
                    emaSlowItem.style.display = 'none';
                }
            }
        });
    }
    
    /**
     * Create trade markers for chart
     * Supports both backtesting format (position_side) and reports format (side)
     */
    createTradeMarkers(trades, options = {}) {
        if (!trades || !Array.isArray(trades) || trades.length === 0) {
            return [];
        }
        
        // Get user's timezone preference and calculate offset (same as processKlineData)
        const useUTC = typeof UserSettings !== 'undefined' && UserSettings.get('timeFormat') === 'utc';
        let timezoneOffsetSeconds = 0;
        if (useUTC) {
            // Get browser's timezone offset in minutes, convert to seconds
            // We ADD the offset to timestamps so local display shows UTC
            timezoneOffsetSeconds = new Date().getTimezoneOffset() * 60; // Convert minutes to seconds
        }
        
        const markers = [];
        const {
            entryTimeField = 'entry_time',
            exitTimeField = 'exit_time',
            entryPriceField = 'entry_price',
            exitPriceField = 'exit_price',
            positionSideField = 'position_side', // backtesting format
            sideField = 'side', // reports format
            exitReasonField = 'exit_reason',
            pnlField = 'net_pnl', // backtesting format
            pnlUsdField = 'pnl_usd', // reports format
        } = options;
        
        trades.forEach(trade => {
            // Entry marker
            if (trade[entryTimeField]) {
                try {
                    const entryDate = new Date(trade[entryTimeField]);
                    if (isNaN(entryDate.getTime())) {
                        console.warn('Invalid entry_time:', trade[entryTimeField]);
                        return;
                    }
                    
                    const baseEntryTime = Math.floor(entryDate.getTime() / 1000);
                    const entryTime = useUTC ? baseEntryTime + timezoneOffsetSeconds : baseEntryTime;
                    const positionSide = trade[positionSideField] || trade[sideField] || 'LONG';
                    const entryPrice = (trade[entryPriceField] !== undefined && trade[entryPriceField] !== null) 
                        ? `$${parseFloat(trade[entryPriceField]).toFixed(4)}` 
                        : '';
                    const entryText = `${positionSide === 'LONG' ? 'BUY' : 'SELL'}${entryPrice ? ' ' + entryPrice : ''}`;
                    
                    markers.push({
                        time: entryTime,
                        position: positionSide === 'LONG' ? 'belowBar' : 'aboveBar',
                        color: positionSide === 'LONG' ? '#26a69a' : '#ef5350',
                        shape: positionSide === 'LONG' ? 'arrowUp' : 'arrowDown',
                        text: entryText,
                        size: 2,
                    });
                } catch (e) {
                    console.warn('Error processing entry marker:', e, trade);
                }
            }
            
            // Exit marker
            if (trade[exitTimeField] && trade[exitPriceField] !== undefined && trade[exitPriceField] !== null) {
                try {
                    const exitDate = new Date(trade[exitTimeField]);
                    if (isNaN(exitDate.getTime())) {
                        console.warn('Invalid exit_time:', trade[exitTimeField]);
                        return;
                    }
                    
                    const baseExitTime = Math.floor(exitDate.getTime() / 1000);
                    const exitTime = useUTC ? baseExitTime + timezoneOffsetSeconds : baseExitTime;
                    const positionSide = trade[positionSideField] || trade[sideField] || 'LONG';
                    
                    // Determine exit color based on PnL and exit reason
                    let exitColor;
                    const pnl = trade[pnlField] !== undefined ? trade[pnlField] : trade[pnlUsdField];
                    
                    if (trade[exitReasonField] === 'TP_TRAILING') {
                        exitColor = '#00c853'; // Bright green
                    } else if (trade[exitReasonField] === 'SL_TRAILING') {
                        exitColor = '#ff9800'; // Orange
                    } else if (pnl !== undefined && pnl !== null && pnl >= 0) {
                        exitColor = '#26a69a'; // Regular profit
                    } else {
                        exitColor = '#ef5350'; // Regular loss
                    }
                    
                    // Build exit text
                    let exitText = 'EXIT';
                    if (trade[exitReasonField]) {
                        const reason = trade[exitReasonField];
                        if (reason === 'TP_TRAILING' || reason === 'SL_TRAILING') {
                            exitText += ` (${reason.replace('_', ' ')} ⚡)`;
                        } else {
                            exitText += ` (${reason})`;
                        }
                    }
                    if (trade[exitPriceField] !== undefined && trade[exitPriceField] !== null) {
                        exitText += ` @ $${parseFloat(trade[exitPriceField]).toFixed(4)}`;
                    }
                    if (pnl !== undefined && pnl !== null) {
                        const pnlSign = pnl >= 0 ? '+' : '';
                        exitText += ` ${pnlSign}$${parseFloat(pnl).toFixed(2)}`;
                    }
                    
                    // Truncate text if too long
                    if (exitText.length > 50) {
                        exitText = exitText.substring(0, 47) + '...';
                    }
                    
                    markers.push({
                        time: exitTime,
                        position: positionSide === 'LONG' ? 'aboveBar' : 'belowBar',
                        color: exitColor,
                        shape: 'circle',
                        text: exitText,
                        size: 1.5,
                    });
                } catch (e) {
                    console.warn('Error processing exit marker:', e, trade);
                }
            }
        });
        
        return markers;
    }
    
    /**
     * Fit chart content to visible area
     */
    fitContent(chart) {
        try {
            chart.timeScale().fitContent();
        } catch (e) {
            console.warn('Error fitting chart content:', e);
        }
    }
}

// Export for use in HTML files
if (typeof window !== 'undefined') {
    window.ChartRenderer = ChartRenderer;
}

