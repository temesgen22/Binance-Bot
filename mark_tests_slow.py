"""
Script to mark non-critical test files as slow.
This helps identify which files should be excluded from CI runs.
"""

# Files to mark as slow (non-critical for CI)
SLOW_TEST_FILES = [
    "test_backtesting.py",
    "test_backtesting_ema_cross_exit.py",
    "test_backtesting_parameters.py",
    "test_backtesting_pagination.py",  # Already has some slow marks
    "test_ema_cross_exit_comprehensive.py",
    "test_live_price_tp_sl.py",  # Comprehensive tests
    "test_strategy_integration.py",  # Already marked slow
    "test_order_idempotency.py",  # Complex state tests
    "test_concurrent_operations.py",  # Has sleeps
    "test_performance_optimizations.py",
    "test_async_database.py",
    "test_datetime_filtering.py",
    "test_chart_time_alignment.py",
    "test_pnl_calculation.py",
    "test_strategy_runner.py",  # Some might be slow
    "test_strategy_registration_async.py",
    "test_strategy_start_stop_times.py",
    "test_binance_parameters.py",
    "test_redis_binance_parameters.py",
    "test_range_mean_reversion.py",
    "test_market_analyzer.py",
    "test_reports.py",
    "test_time_handling.py",
    "test_multi_account.py",
    "test_circuit_breaker.py",
    "test_structured_logging.py",
]

# Note: Already marked slow via class-level markers:
# - test_redis_database_integration.py (TestRedisDatabaseIntegration)
# - test_redis_persistence.py (TestRedisPersistenceIntegration)
# - test_notifier.py (TestNotificationIntegration)
# - test_indicators.py (TestIndicatorIntegration)
# - test_log_viewer.py (TestLogViewerIntegration)
# - test_order_execution.py (TestOrderExecutionIntegration)
# - test_strategy_scalping.py (TestIntegration)
# - test_health_checks.py (various slow tests)
# - test_telegram_commands.py (various slow tests)
# - test_metrics.py (slow test)
# - test_correlation_id.py (slow test)
# - test_test_accounts.py (slow test)


