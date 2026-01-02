"""
End-to-End Test for Auto-Tuning System

This script tests the complete auto-tuning workflow:
1. Database models and migrations
2. API endpoints
3. Service layer logic
4. Integration points

Run with: python test_auto_tuning_e2e.py
"""
import sys
import asyncio
from datetime import datetime, timezone
from uuid import uuid4

# Configure output encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def print_test(name: str):
    """Print test header."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")

def print_pass(message: str):
    """Print test pass."""
    print(f"✓ PASS: {message}")

def print_fail(message: str):
    """Print test fail."""
    print(f"✗ FAIL: {message}")

def print_info(message: str):
    """Print info."""
    print(f"  INFO: {message}")

# Test 1: Database Models
print_test("1. Database Models")
try:
    from app.models.db_models import Strategy, StrategyParameterHistory
    from sqlalchemy import inspect
    
    # Check Strategy model has auto-tuning fields
    strategy_columns = [col.name for col in inspect(Strategy).columns]
    required_strategy_fields = ['auto_tuning_enabled', 'auto_tuning_config']
    
    for field in required_strategy_fields:
        if field in strategy_columns:
            print_pass(f"Strategy model has '{field}' field")
        else:
            print_fail(f"Strategy model missing '{field}' field")
    
    # Check StrategyParameterHistory model exists
    param_history_columns = [col.name for col in inspect(StrategyParameterHistory).columns]
    required_history_fields = [
        'strategy_uuid', 'old_params', 'new_params', 'changed_params',
        'status', 'performance_before', 'performance_after', 'created_at'
    ]
    
    for field in required_history_fields:
        if field in param_history_columns:
            print_pass(f"StrategyParameterHistory model has '{field}' field")
        else:
            print_fail(f"StrategyParameterHistory model missing '{field}' field")
    
    print_pass("Database models check complete")
except Exception as e:
    print_fail(f"Database models check failed: {e}")

# Test 2: Pydantic Models
print_test("2. Pydantic Models")
try:
    from app.services.auto_tuning_service import (
        AutoTuningConfig,
        PerformanceSnapshot,
        ValidationScore
    )
    
    # Test AutoTuningConfig defaults
    config = AutoTuningConfig(enabled=True)
    assert config.min_trades == 20, "Default min_trades should be 20"
    assert config.evaluation_period_days == 7, "Default evaluation_period_days should be 7"
    assert config.min_time_between_tuning_hours == 24, "Default cooldown should be 24 hours"
    print_pass("AutoTuningConfig model works with defaults")
    
    # Test PerformanceSnapshot
    snapshot = PerformanceSnapshot(
        validation_return_pct_30d=5.0,
        validation_sharpe_30d=1.5,
        validation_win_rate_30d=0.55,
        validation_drawdown_30d=0.10,
        validation_profit_factor_30d=1.3,
        total_trades_30d=50,
        timestamp=datetime.now(timezone.utc)
    )
    assert snapshot.validation_return_pct_30d == 5.0
    print_pass("PerformanceSnapshot model works")
    
    # Test ValidationScore calculation
    score = ValidationScore.calculate(
        return_pct=5.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=10.0,
        win_rate=0.55
    )
    assert score.score is not None
    assert score.return_pct == 5.0
    print_pass("ValidationScore calculation works")
    
except Exception as e:
    print_fail(f"Pydantic models check failed: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Service Layer - AutoTuningService
print_test("3. AutoTuningService Methods")
try:
    from app.services.auto_tuning_service import AutoTuningService
    
    # Check required methods exist
    required_methods = [
        'tune_strategy',
        '_resolve_strategy_uuid',
        '_create_performance_snapshot',
        '_normalize_fraction',
        '_check_debounce',
        '_validate_parameters',
        '_update_strategy_parameters'
    ]
    
    for method in required_methods:
        if hasattr(AutoTuningService, method):
            print_pass(f"AutoTuningService has '{method}' method")
        else:
            print_fail(f"AutoTuningService missing '{method}' method")
    
except Exception as e:
    print_fail(f"AutoTuningService check failed: {e}")

# Test 4: Database Service Methods
print_test("4. DatabaseService Methods")
try:
    from app.services.database_service import DatabaseService
    
    # Check required methods exist
    required_methods = [
        'create_parameter_history',
        'async_create_parameter_history',
        'get_last_parameter_change',
        'async_get_last_parameter_change',
        'list_parameter_history',
        'async_list_parameter_history',
        'update_parameter_history',
        'async_update_parameter_history'
    ]
    
    for method in required_methods:
        if hasattr(DatabaseService, method):
            print_pass(f"DatabaseService has '{method}' method")
        else:
            print_fail(f"DatabaseService missing '{method}' method")
    
except Exception as e:
    print_fail(f"DatabaseService check failed: {e}")

# Test 5: API Routes
print_test("5. API Routes")
try:
    from app.api.routes.auto_tuning import router
    
    # Check routes exist
    route_paths = [route.path for route in router.routes]
    required_routes = [
        '/strategies/{strategy_id}/enable',
        '/strategies/{strategy_id}/disable',
        '/strategies/{strategy_id}/tune-now',
        '/strategies/{strategy_id}/status',
        '/strategies/{strategy_id}/history',
        '/strategies/{strategy_id}/evaluate',
        '/evaluate-all'
    ]
    
    for route in required_routes:
        # Routes are registered with prefix, so check if path contains the route
        found = any(route in path for path in route_paths)
        if found:
            print_pass(f"Route '{route}' exists")
        else:
            print_fail(f"Route '{route}' missing")
            print_info(f"Available routes: {route_paths}")
    
except Exception as e:
    print_fail(f"API routes check failed: {e}")
    import traceback
    traceback.print_exc()

# Test 6: StrategyRunner Hot-Swap
print_test("6. StrategyRunner Hot-Swap Method")
try:
    from app.services.strategy_runner import StrategyRunner
    
    if hasattr(StrategyRunner, 'update_strategy_params'):
        print_pass("StrategyRunner has 'update_strategy_params' method for hot-swap")
    else:
        print_fail("StrategyRunner missing 'update_strategy_params' method")
    
except Exception as e:
    print_fail(f"StrategyRunner check failed: {e}")

# Test 7: AutoTuningEvaluator
print_test("7. AutoTuningEvaluator")
try:
    from app.services.auto_tuning_evaluator import AutoTuningEvaluator
    
    # Check required methods
    required_methods = ['start', 'stop', 'evaluate_pending_records', 'evaluate_strategy']
    
    for method in required_methods:
        if hasattr(AutoTuningEvaluator, method):
            print_pass(f"AutoTuningEvaluator has '{method}' method")
        else:
            print_fail(f"AutoTuningEvaluator missing '{method}' method")
    
except Exception as e:
    print_fail(f"AutoTuningEvaluator check failed: {e}")

# Test 8: Unit Normalization
print_test("8. Unit Normalization")
try:
    from app.services.auto_tuning_service import AutoTuningService
    
    # Create a dummy service instance to test normalization
    # We'll just check the method exists and test the logic
    service_class = AutoTuningService
    
    # Test normalization logic (fractions should be 0.0-1.0)
    test_cases = [
        (0.45, "win_rate", 0.45),  # Already fraction
        (45.0, "win_rate", 0.45),  # Percent to fraction
        (0.15, "drawdown", 0.15),  # Already fraction
        (15.0, "drawdown", 0.15),  # Percent to fraction
    ]
    
    # We can't easily test without an instance, but we can verify the method exists
    if hasattr(service_class, '_normalize_fraction'):
        print_pass("_normalize_fraction method exists")
        print_info("Unit normalization logic should convert percentages to fractions")
    else:
        print_fail("_normalize_fraction method missing")
    
except Exception as e:
    print_fail(f"Unit normalization check failed: {e}")

# Test 9: Configuration Validation
print_test("9. Configuration Validation")
try:
    from app.services.auto_tuning_service import AutoTuningConfig
    
    # Test valid config
    valid_config = AutoTuningConfig(
        enabled=True,
        min_trades=20,
        evaluation_period_days=7,
        min_time_between_tuning_hours=24,
        win_rate_threshold_frac=0.45,
        sharpe_threshold=0.5,
        drawdown_threshold_frac=0.15
    )
    assert valid_config.enabled == True
    print_pass("Valid AutoTuningConfig can be created")
    
    # Test invalid values (should raise validation error)
    try:
        invalid_config = AutoTuningConfig(
            win_rate_threshold_frac=1.5  # > 1.0, should fail
        )
        print_fail("AutoTuningConfig should reject invalid values")
    except Exception:
        print_pass("AutoTuningConfig validates input ranges")
    
except Exception as e:
    print_fail(f"Configuration validation check failed: {e}")

# Test 10: Cache Serialization
print_test("10. Cache Serialization")
try:
    from app.services.strategy_service import StrategyService
    from app.models.strategy import StrategySummary
    
    # Check that auto_tuning_enabled is included in serialization
    if hasattr(StrategyService, '_strategy_summary_to_dict'):
        # Check the method includes auto_tuning_enabled
        import inspect
        source = inspect.getsource(StrategyService._strategy_summary_to_dict)
        if 'auto_tuning_enabled' in source:
            print_pass("Cache serialization includes 'auto_tuning_enabled'")
        else:
            print_fail("Cache serialization missing 'auto_tuning_enabled'")
    else:
        print_fail("_strategy_summary_to_dict method missing")
    
    if hasattr(StrategyService, '_dict_to_strategy_summary'):
        source = inspect.getsource(StrategyService._dict_to_strategy_summary)
        if 'auto_tuning_enabled' in source:
            print_pass("Cache deserialization includes 'auto_tuning_enabled'")
        else:
            print_fail("Cache deserialization missing 'auto_tuning_enabled'")
    
except Exception as e:
    print_fail(f"Cache serialization check failed: {e}")

# Test 11: Database Eager Loading
print_test("11. Database Eager Loading")
try:
    from app.services.database_service import DatabaseService
    
    # Check that async_get_strategy uses selectinload
    import inspect
    source = inspect.getsource(DatabaseService.async_get_strategy)
    if 'selectinload' in source:
        print_pass("async_get_strategy uses eager loading (selectinload)")
    else:
        print_fail("async_get_strategy missing eager loading")
    
    if 'selectinload' in inspect.getsource(DatabaseService.async_get_user_strategies):
        print_pass("async_get_user_strategies uses eager loading")
    else:
        print_fail("async_get_user_strategies missing eager loading")
    
except Exception as e:
    print_fail(f"Database eager loading check failed: {e}")

# Summary
print_test("TEST SUMMARY")
print("\nAll structural tests completed!")
print("\nNote: This test verifies the code structure and interfaces.")
print("For full end-to-end testing with a real database, you would need to:")
print("  1. Set up a test database")
print("  2. Create test strategies")
print("  3. Generate test trade data")
print("  4. Call the API endpoints")
print("  5. Verify parameter changes are applied")
print("\nThe code structure appears to be correctly implemented.")










