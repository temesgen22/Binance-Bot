# Log Viewer GUI Test Cases

## Overview

Comprehensive test suite for the Log Viewer GUI and API endpoints. The tests verify all functionality including log parsing, filtering, API endpoints, and static file serving.

## Test Coverage

### 1. Log Parsing Tests (`TestLogParsing`)

Tests the core log line parsing functionality:

- ✅ **Valid log line parsing** - Verifies correct parsing of standard log format
- ✅ **Different log levels** - Tests DEBUG, INFO, ERROR levels
- ✅ **Symbol extraction** - Verifies cryptocurrency symbols in messages
- ✅ **Special characters** - Tests handling of special characters in messages
- ✅ **Invalid log lines** - Ensures invalid lines return `None`

**Key Test Cases:**
- `test_parse_valid_log_line()` - Standard INFO log
- `test_parse_debug_log_line()` - DEBUG level log
- `test_parse_error_log_line()` - ERROR level log
- `test_parse_log_with_symbol()` - Log containing trading symbol
- `test_parse_invalid_log_line()` - Various invalid formats
- `test_parse_log_with_special_characters()` - Special chars in messages

### 2. Log Filtering Tests (`TestLogFiltering`)

Tests the filtering logic for log entries:

- ✅ **Symbol filtering** - Filter by cryptocurrency symbol (case-insensitive)
- ✅ **Level filtering** - Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- ✅ **Date filtering** - Filter by date range (from/to)
- ✅ **Module filtering** - Filter by Python module name
- ✅ **Function filtering** - Filter by function name
- ✅ **Search text** - Full-text search across messages
- ✅ **Multiple criteria** - Combined filters
- ✅ **No matches** - Edge case with no matching entries

**Key Test Cases:**
- `test_filter_by_symbol()` - BTCUSDT, ETHUSDT filtering
- `test_filter_by_level()` - ERROR level filtering
- `test_filter_by_date_from()` - Start date filtering
- `test_filter_by_date_to()` - End date filtering
- `test_filter_by_date_range()` - Date range filtering
- `test_filter_by_module()` - Module name filtering
- `test_filter_by_function()` - Function name filtering
- `test_filter_by_search_text()` - Text search
- `test_filter_multiple_criteria()` - Combined filters
- `test_filter_case_insensitive_symbol()` - Case-insensitive symbol matching

### 3. API Endpoint Tests (`TestLogAPIEndpoints`)

Tests all REST API endpoints:

- ✅ **GET /logs/** - Main log retrieval endpoint
- ✅ **GET /logs/symbols** - Symbol extraction endpoint
- ✅ **GET /logs/stats** - Statistics endpoint
- ✅ **Query parameters** - All filter parameters
- ✅ **Response format** - Valid JSON structure
- ✅ **Edge cases** - No log files, invalid dates, limits

**Key Test Cases:**
- `test_get_logs_endpoint()` - Basic log retrieval
- `test_get_logs_with_symbol_filter()` - Symbol filtering via API
- `test_get_logs_with_level_filter()` - Level filtering via API
- `test_get_logs_with_date_filter()` - Date filtering via API
- `test_get_logs_with_limit()` - Result limiting
- `test_get_logs_with_search_text()` - Text search via API
- `test_get_logs_no_files()` - No log files scenario
- `test_get_logs_with_module_filter()` - Module filtering
- `test_get_logs_with_function_filter()` - Function filtering
- `test_get_logs_reverse_order()` - Reverse chronological ordering
- `test_get_logs_symbols_endpoint()` - Symbol list endpoint
- `test_get_logs_stats_endpoint()` - Statistics endpoint

### 4. Static File Serving Tests (`TestStaticFileServing`)

Tests the web GUI static files:

- ✅ **Static file access** - HTML file is served correctly
- ✅ **Root redirect** - Root URL redirects to GUI
- ✅ **Content type** - Correct MIME types

**Key Test Cases:**
- `test_static_index_html_exists()` - GUI HTML is accessible
- `test_root_redirects_to_gui()` - Root URL redirect behavior

### 5. Integration Tests (`TestLogViewerIntegration`)

End-to-end workflow tests:

- ✅ **Complete filtering workflow** - Multiple filters combined
- ✅ **Symbol extraction** - Real-world symbol detection
- ✅ **Statistics calculation** - Accurate stat computation
- ✅ **Error handling** - Invalid inputs handled gracefully
- ✅ **Parameter validation** - Limit and date validation

**Key Test Cases:**
- `test_full_filter_workflow()` - Complete user workflow
- `test_symbol_extraction()` - Symbol detection from logs
- `test_statistics_calculation()` - Stats accuracy
- `test_invalid_date_format_handled_gracefully()` - Error handling
- `test_limit_validation()` - Parameter validation

## Running the Tests

### Run All Log Viewer Tests

```bash
pytest tests/test_log_viewer.py -v
```

### Run Specific Test Classes

```bash
# Test log parsing only
pytest tests/test_log_viewer.py::TestLogParsing -v

# Test API endpoints only
pytest tests/test_log_viewer.py::TestLogAPIEndpoints -v

# Test filtering only
pytest tests/test_log_viewer.py::TestLogFiltering -v
```

### Run Specific Test Cases

```bash
# Test symbol filtering
pytest tests/test_log_viewer.py::TestLogFiltering::test_filter_by_symbol -v

# Test API endpoint
pytest tests/test_log_viewer.py::TestLogAPIEndpoints::test_get_logs_endpoint -v
```

### Run with Coverage

```bash
pytest tests/test_log_viewer.py --cov=app.api.routes.logs --cov-report=html
```

## Test Data

Tests use mock log files with the following sample entries:

```
2025-11-24 01:00:00 | INFO     | app.services.strategy_runner:_execute:100 | Order placed for BTCUSDT
2025-11-24 02:00:00 | DEBUG    | app.strategies.scalping:evaluate:50 | EMA calculation for ETHUSDT
2025-11-24 03:00:00 | ERROR    | app.core.my_binance_client:place_order:200 | Failed to place order for BTCUSDT: Insufficient funds
2025-11-25 01:00:00 | INFO     | app.services.strategy_runner:_run_loop:150 | Strategy started for ETHUSDT
```

## Expected Test Results

All tests should pass with the following metrics:

- **Total Tests**: ~30+ test cases
- **Coverage**: 100% of log viewer functionality
- **Execution Time**: < 2 seconds
- **Pass Rate**: 100%

## Common Issues and Fixes

### Issue: Mock file reading not working

**Fix**: Ensure `@patch("builtins.open")` is used correctly with `mock_open`

### Issue: Tests failing due to missing log files

**Fix**: Tests use mocked file reading, so actual log files are not required

### Issue: Static file tests failing

**Fix**: Ensure `app/static/index.html` exists in the project

## Test Validation Checklist

- [ ] All log parsing tests pass
- [ ] All filtering tests pass
- [ ] All API endpoint tests pass
- [ ] Static file serving works
- [ ] Integration tests pass
- [ ] No linting errors
- [ ] Tests run in < 2 seconds
- [ ] 100% code coverage for log viewer

## Continuous Integration

These tests are automatically run in the Jenkins CI/CD pipeline:

```groovy
stage('Run Log Viewer Tests') {
    steps {
        sh 'pytest tests/test_log_viewer.py -v'
    }
}
```

## Future Enhancements

Potential test additions:

- [ ] Test compressed log file reading (.zip)
- [ ] Test rotated log files (bot.log.1, bot.log.2)
- [ ] Test concurrent access to log files
- [ ] Test performance with large log files (10,000+ entries)
- [ ] Test GUI JavaScript functionality (Selenium/Playwright)

