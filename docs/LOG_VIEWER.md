# Log Viewer GUI Documentation

## Overview

The Binance Bot includes a web-based GUI for viewing and filtering bot logs in real-time. The interface provides powerful filtering capabilities and an intuitive design for monitoring bot activity.

## Accessing the GUI

Once the FastAPI server is running, access the log viewer by navigating to:

```
http://localhost:8000/
```

Or directly:
```
http://localhost:8000/static/index.html
```

## Features

### 1. **Comprehensive Filtering**

The GUI supports multiple filter options:

- **Cryptocurrency Symbol**: Filter logs by trading symbol (e.g., BTCUSDT, ETHUSDT)
  - Auto-complete suggestions are available for all symbols found in logs
  
- **Log Level**: Filter by log severity
  - DEBUG, INFO, WARNING, ERROR, CRITICAL
  - Select "All Levels" to see everything

- **Date Range**: Filter logs by date
  - From Date: Start date (YYYY-MM-DD)
  - To Date: End date (YYYY-MM-DD)
  - Default: Last 7 days

- **Module**: Filter by Python module path
  - e.g., `strategy_runner`, `my_binance_client`

- **Function**: Filter by function name
  - e.g., `_execute`, `place_order`

- **Search Text**: Full-text search across messages, modules, and functions
  - Case-insensitive search

- **Max Results**: Limit the number of entries returned (1-10,000)
  - Default: 1000 entries

### 2. **Real-Time Updates**

- **Auto Refresh**: Enable automatic refresh every 5 seconds
  - Toggle the checkbox to start/stop auto-refresh
  - Useful for monitoring live bot activity

- **Manual Refresh**: Click "Load Logs" to refresh manually

### 3. **Log Entry Display**

Each log entry shows:

- **Timestamp**: When the log was created
- **Level**: Log severity with color-coded badges
- **Module Path**: Python module that generated the log
- **Function**: Function name and line number
- **Message**: The actual log message

Color coding:
- 🔵 **DEBUG**: Gray
- 🔵 **INFO**: Cyan
- 🟡 **WARNING**: Yellow
- 🔴 **ERROR**: Red (with light red background)
- 🔴 **CRITICAL**: Dark red (with light red background)

### 4. **Interactive Features**

- **Click to Copy**: Click any log entry to copy its raw content to clipboard
- **Export Logs**: Export filtered logs as a text file
  - File name includes the export date
- **Clear Filters**: Reset all filters to defaults

### 5. **Statistics Bar**

The top bar displays:
- **Total Entries**: Total number of log entries found
- **Filtered**: Number of entries matching current filters
- **Status**: Current loading/error status

## API Endpoints

The GUI uses the following REST API endpoints:

### GET `/logs/`

Get filtered log entries.

**Query Parameters:**
- `symbol` (optional): Cryptocurrency symbol filter
- `level` (optional): Log level filter
- `date_from` (optional): Start date (YYYY-MM-DD)
- `date_to` (optional): End date (YYYY-MM-DD)
- `search_text` (optional): Text search
- `module` (optional): Module name filter
- `function` (optional): Function name filter
- `limit` (optional, default: 1000): Maximum entries to return
- `reverse` (optional, default: true): Reverse chronological order

**Response:**
```json
{
  "entries": [
    {
      "timestamp": "2025-11-24 01:18:35",
      "level": "INFO",
      "module": "app.services.strategy_runner",
      "function": "_load_from_redis",
      "line": 299,
      "message": "Redis not enabled, skipping load from Redis",
      "raw_line": "..."
    }
  ],
  "total_count": 1000,
  "filtered_count": 50
}
```

### GET `/logs/symbols`

Get list of unique cryptocurrency symbols found in logs.

**Response:**
```json
["BTCUSDT", "ETHUSDT", "BNBUSDT", ...]
```

### GET `/logs/stats`

Get statistics about the logs.

**Response:**
```json
{
  "total_files": 1,
  "total_compressed": 2,
  "levels": {
    "INFO": 500,
    "DEBUG": 300,
    "ERROR": 10
  },
  "modules": {
    "app.services.strategy_runner": 400,
    "app.core.my_binance_client": 200
  },
  "first_entry": "2025-11-24T01:18:35",
  "last_entry": "2025-11-26T17:51:15",
  "total_entries": 810
}
```

## Use Cases

### Monitor Specific Trading Pairs

1. Enter a symbol in the "Cryptocurrency Symbol" field (e.g., `BTCUSDT`)
2. Click "Load Logs"
3. View all logs related to that trading pair

### Debug Errors

1. Select "ERROR" or "CRITICAL" from the "Log Level" dropdown
2. Optionally add a date range to focus on recent errors
3. Click "Load Logs"
4. Review error messages and their context

### Track Strategy Execution

1. Enter the module name (e.g., `strategy_runner`) in the "Module" field
2. Optionally enter a function name (e.g., `_execute`)
3. Click "Load Logs"
4. Monitor strategy execution flow

### Monitor Order Execution

1. Use "Search Text" to search for keywords like "order", "BUY", "SELL", "FILLED"
2. Optionally filter by symbol
3. Enable auto-refresh to see new orders in real-time

### Export Logs for Analysis

1. Apply desired filters
2. Click "Export Logs"
3. A text file will be downloaded with all filtered log entries

## Technical Details

### Log File Location

Logs are stored in the `logs/` directory:
- Main log file: `logs/bot.log`
- Rotated logs: `logs/bot.log.1`, `logs/bot.log.2`, etc.
- Compressed logs: `logs/bot.log.YYYY-MM-DD.zip`

### Log Format

The log viewer expects the following format:
```
{timestamp} | {level} | {module}:{function}:{line} | {message}
```

Example:
```
2025-11-24 01:18:35 | INFO     | app.services.strategy_runner:_load_from_redis:299 | Redis not enabled
```

### Performance Considerations

- Large log files (>10MB) may take a few seconds to load
- The default limit of 1000 entries provides a good balance between performance and visibility
- Enable auto-refresh with caution on large log files to avoid excessive server load

## Troubleshooting

### GUI Not Loading

1. Ensure the FastAPI server is running
2. Check that the `app/static/index.html` file exists
3. Verify static files are being served correctly (check server logs)

### No Logs Displayed

1. Verify that log files exist in the `logs/` directory
2. Check that log files are readable
3. Try clearing all filters and loading logs
4. Check the browser console for JavaScript errors

### Filtering Not Working

1. Verify the date format is YYYY-MM-DD
2. Check that symbol names are uppercase (e.g., BTCUSDT, not btcusdt)
3. Ensure log level names match exactly (DEBUG, INFO, WARNING, ERROR, CRITICAL)

### Auto-Refresh Issues

1. Check browser console for network errors
2. Verify the server is still running
3. If auto-refresh is consuming too many resources, reduce the refresh interval in the JavaScript code

## Browser Compatibility

The GUI is tested and works with:
- Chrome/Edge (Chromium-based)
- Firefox
- Safari

For best experience, use a modern browser with JavaScript enabled.

