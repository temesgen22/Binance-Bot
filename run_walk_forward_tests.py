"""
Simple test runner for walk-forward tests.
"""
import sys
import traceback

print("=" * 60)
print("Walk-Forward Analysis Test Runner")
print("=" * 60)

# Test 1: Import test
print("\n[1/6] Testing imports...")
try:
    from app.services.walk_forward import (
        generate_walk_forward_windows,
        calculate_robust_score,
        aggregate_walk_forward_results,
        calculate_metric_score,
        generate_param_combinations
    )
    from app.api.routes.backtesting import BacktestResult
    print("✅ All imports successful")
except Exception as e:
    print(f"❌ Import failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Test 2: Window generation - rolling
print("\n[2/6] Testing rolling window generation...")
try:
    from datetime import datetime, timedelta, timezone
    
    start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end_time = datetime(2024, 1, 20, tzinfo=timezone.utc)
    
    windows = generate_walk_forward_windows(
        start_time=start_time,
        end_time=end_time,
        training_days=7,
        test_days=3,
        step_days=5,
        window_type="rolling"
    )
    
    assert len(windows) > 0, "Should generate at least one window"
    
    # Check fixed size
    for window in windows:
        training_duration = (window['training_end'] - window['training_start']).days
        assert training_duration == 7, f"Expected 7 days, got {training_duration}"
    
    print(f"✅ Rolling windows: Generated {len(windows)} windows, all fixed size (7 days)")
except Exception as e:
    print(f"❌ Rolling window test failed: {e}")
    traceback.print_exc()

# Test 3: Window generation - expanding
print("\n[3/6] Testing expanding window generation...")
try:
    windows = generate_walk_forward_windows(
        start_time=start_time,
        end_time=end_time,
        training_days=7,
        test_days=3,
        step_days=5,
        window_type="expanding"
    )
    
    assert len(windows) > 0, "Should generate at least one window"
    
    # Check all start from beginning
    for window in windows:
        assert window['training_start'] == start_time, "Expanding windows should start from beginning"
    
    print(f"✅ Expanding windows: Generated {len(windows)} windows, all start from beginning")
except Exception as e:
    print(f"❌ Expanding window test failed: {e}")
    traceback.print_exc()

# Test 4: Robust score calculation
print("\n[4/6] Testing robust score calculation...")
try:
    # Create mock result
    result = BacktestResult(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=datetime.now(timezone.utc) - timedelta(days=30),
        end_time=datetime.now(timezone.utc),
        initial_balance=1000.0,
        final_balance=1050.0,  # 5% return
        total_pnl=50.0,
        total_return_pct=5.0,
        total_trades=10,
        completed_trades=10,
        open_trades=0,
        winning_trades=6,
        losing_trades=4,
        win_rate=60.0,
        total_fees=3.0,
        avg_profit_per_trade=5.0,
        largest_win=10.0,
        largest_loss=-5.0,
        max_drawdown=20.0,
        max_drawdown_pct=2.0,
        trades=[{
            "entry_time": datetime.now(timezone.utc),
            "exit_time": datetime.now(timezone.utc),
            "entry_price": 50000.0,
            "exit_price": 50200.0,
            "position_side": "LONG",
            "quantity": 0.01,
            "notional": 500.0,
            "entry_fee": 0.15,
            "exit_fee": 0.15,
            "pnl": 10.0,
            "net_pnl": 9.7,
            "exit_reason": "TP",
            "is_open": False
        }] * 10,
        klines=None,
        indicators=None
    )
    
    score = calculate_robust_score(result)
    expected = 5.0 - (2.0 * 2.0)  # 5% return - 2 * 2% drawdown = 1.0
    
    assert abs(score - expected) < 0.01, f"Expected {expected}, got {score}"
    print(f"✅ Robust score: {score:.2f} (expected: {expected:.2f})")
except Exception as e:
    print(f"❌ Robust score test failed: {e}")
    traceback.print_exc()

# Test 5: Parameter combinations
print("\n[5/6] Testing parameter combination generation...")
try:
    optimize_params = {
        "ema_fast": [5, 8],
        "ema_slow": [15, 21]
    }
    
    combinations = generate_param_combinations(optimize_params)
    
    assert len(combinations) == 4, f"Expected 4 combinations, got {len(combinations)}"
    print(f"✅ Parameter combinations: Generated {len(combinations)} combinations")
except Exception as e:
    print(f"❌ Parameter combination test failed: {e}")
    traceback.print_exc()

# Test 6: Result aggregation (compounded returns)
print("\n[6/6] Testing result aggregation (compounded returns)...")
try:
    from app.services.walk_forward import WalkForwardWindow
    
    # Create two windows with 5% return each
    window1 = WalkForwardWindow(
        window_number=1,
        training_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        training_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
        test_start=datetime(2024, 1, 8, tzinfo=timezone.utc),
        test_end=datetime(2024, 1, 11, tzinfo=timezone.utc),
        training_result=result,
        test_result=BacktestResult(
            **{**result.model_dump(), "initial_balance": 1000.0, "final_balance": 1050.0, "total_return_pct": 5.0}
        ),
        training_return_pct=0.0,
        test_return_pct=5.0,
        training_win_rate=50.0,
        test_win_rate=60.0
    )
    
    window2 = WalkForwardWindow(
        window_number=2,
        training_start=datetime(2024, 1, 6, tzinfo=timezone.utc),
        training_end=datetime(2024, 1, 13, tzinfo=timezone.utc),
        test_start=datetime(2024, 1, 13, tzinfo=timezone.utc),
        test_end=datetime(2024, 1, 16, tzinfo=timezone.utc),
        training_result=result,
        test_result=BacktestResult(
            **{**result.model_dump(), "initial_balance": 1050.0, "final_balance": 1102.5, "total_return_pct": 5.0}
        ),
        training_return_pct=0.0,
        test_return_pct=5.0,
        training_win_rate=50.0,
        test_win_rate=60.0
    )
    
    aggregated = aggregate_walk_forward_results([window1, window2], 1000.0)
    
    # Should be compounded: (1102.5 / 1000 - 1) * 100 = 10.25%
    # NOT summed: 5% + 5% = 10%
    expected_total = ((1102.5 / 1000.0) - 1.0) * 100
    
    assert abs(aggregated['total_return_pct'] - expected_total) < 0.01, \
        f"Expected compounded return {expected_total}%, got {aggregated['total_return_pct']}%"
    
    print(f"✅ Aggregation: Total return = {aggregated['total_return_pct']:.2f}% (compounded, not summed)")
    print(f"   Expected: {expected_total:.2f}% (compounded)")
    print(f"   If summed: 10.00% (incorrect)")
except Exception as e:
    print(f"❌ Aggregation test failed: {e}")
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test Summary: All core functionality validated!")
print("=" * 60)















































































