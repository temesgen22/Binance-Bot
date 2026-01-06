# Test Configuration for CI/CD

## Overview

This document describes how tests are configured for CI/CD environments (e.g., Jenkins). **Tests are EXCLUDED during deployment by default** to save CPU resources.

## CI Test Marking Strategy

Due to CPU resource limitations in Jenkins, **only essential, fast tests are run by default**. Tests are marked with `@pytest.mark.ci` to indicate they are critical and should run in CI/CD.

### Configuration

The `pytest.ini` file has **NO default test execution** - tests are excluded during deployment:

```ini
# addopts = -m ci  # Commented out - tests excluded during deployment
```

**Tests do NOT run automatically** - they must be explicitly invoked.

### Running Tests

#### During Deployment (Jenkins) - Default Behavior
```bash
# Tests are SKIPPED by default during deployment
# No test execution happens automatically
```

#### Enable Tests in Jenkins (Optional)
Set environment variable in Jenkins:
```groovy
environment {
  RUN_TESTS = 'true'  // Enable test stage
}
```

Or run tests manually:
```bash
# Run CI-marked tests (fast, essential tests)
pytest -m ci

# Run all tests
pytest -m ""

# Run slow tests
pytest -m slow
```

#### Run All Tests (Local Development/Full Suite)
```bash
# Run all tests (remove marker filter)
pytest -m ""  # Empty marker = all tests

# Or temporarily modify pytest.ini
```

#### Run Slow Tests Only
```bash
# Run only slow tests
pytest -m slow
```

### Currently Marked CI Tests (~111 tests)

#### Critical Function Tests (All)
- `test_critical_functions.py` - **All tests marked** (module-level marker)
  - EMA calculation accuracy
  - Crossover detection logic
  - State management (prev_fast/prev_slow)
  - TP/SL calculations
  - Filter logic

#### Parameter Contract Tests (All)
- `test_parameter_contracts.py` - **All tests marked** (module-level marker)
  - Risk parameter validation
  - Strategy parameter behavior

#### Critical Edge Cases (All)
- `test_scalping_critical_edge_cases.py` - **All tests marked** (module-level marker)
  - HTF bias fail-closed behavior
  - EMA history drift prevention
  - Trailing stop on entry candle
  - Interval validation fallback
  - Candle-time monotonicity
  - Separation filter behavior
  - Position state sync

#### Strategy Scalping Unit Tests
- `TestConfigurationMapping` - Configuration parameter validation
- `TestEMACalculation` - Core EMA calculation logic
- `TestCrossoverDetection` - Entry/exit signal detection
- `TestTakeProfitStopLoss` - TP/SL calculation logic
- `TestFilters` - Cooldown, separation, HTF bias filters
- `TestStateConsistency` - State tracking (prev_fast/prev_slow)

#### Critical Race Conditions (Essential Only)
- `test_tc01_start_same_strategy_twice_concurrently` - Prevents duplicate starts
- `test_tc02_start_two_strategies_when_max_concurrent_is_one` - Max concurrent enforcement

#### Backtesting Pagination (Bug Fix Tests Only)
- `test_bug_fix_removed_futures_historical_klines` - Critical bug fix verification
- `test_pagination_threshold_500_ensures_reliability` - Pagination threshold fix
- `test_pagination_threshold_500_candles` - Threshold validation

### Test Counts

- **Total Tests**: ~672
- **CI Tests**: ~111 (run in CI/CD - fast and essential)
- **Excluded Tests**: ~561 (not run in CI/CD due to CPU limitations)

### Benefits

1. **CPU Resource Management**: Prevents resource exhaustion in Jenkins
2. **Fast CI/CD**: Deployment pipelines run in ~1-2 minutes instead of 6+ minutes
3. **Essential Coverage**: Critical functionality is still tested
4. **Selective Testing**: Full suite can be run locally or in scheduled builds

### Recommendations

1. **CI/CD (Jenkins)**: Use default configuration (`-m ci`) - only essential tests
2. **Local Development**: Run full suite before committing: `pytest -m ""`
3. **Nightly Builds**: Optionally run full suite including slow tests
4. **Pre-merge**: Consider running full suite for critical changes

### Example Jenkins Configuration

```groovy
stage('Tests') {
    steps {
        // Only run essential CI tests (fast, low CPU usage)
        sh 'pytest -m ci --tb=short -v'
    }
}

stage('Full Test Suite (Optional)') {
    when {
        // Run on nightly builds or release branches
        anyOf {
            branch 'main'
            cron('H 2 * * *')  // Nightly at 2 AM
        }
    }
    steps {
        // Run all tests (may take longer, use more CPU)
        sh 'pytest -m "" --tb=short -v'
    }
}
```

### Test Categories

- **CI Tests (`@pytest.mark.ci`)**: Fast, essential, no external dependencies
- **Slow Tests (`@pytest.mark.slow`)**: Comprehensive, integration, performance tests
- **Unmarked Tests**: Regular tests that are not critical for CI but should run in full suite

