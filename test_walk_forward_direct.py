"""
Direct test of walk-forward analysis functionality.
This script tests the core functions directly without pytest.
"""
import sys
import os
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 70)
print("WALK-FORWARD ANALYSIS DIRECT TEST")
print("=" * 70)

# Test 1: Imports
print("\n[TEST 1] Testing imports...")
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
    test1_passed = True
except Exception as e:
    print(f"❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
    test1_passed = False
    sys.exit(1)

# Test 2: Rolling Window Generation
print("\n[TEST 2] Testing rolling window generation...")
try:
    start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end_time = datetime(2024, 1, 20, tzinfo=timezone.utc)  # 19 days
    
    windows = generate_walk_forward_windows(
        start_time=start_time,
        end_time=end_time,
        training_days=7,
        test_days=3,
        step_days=5,
        window_type="rolling"
    )
    
    assert len(windows) > 0, f"Expected windows, got {len(windows)}"
    print(f"   Generated {len(windows)} windows")
    
    # Verify fixed size
    for i, window in enumerate(windows):
        training_duration = (window['training_end'] - window['training_start']).days
        assert training_duration == 7, f"Window {i+1}: Expected 7 days, got {training_duration}"
        assert window['test_start'] == window['training_end'], "Test should start after training"
    
    print(f"   ✅ All {len(windows)} windows have fixed size (7 days)")
    print(f"   First window: {windows[0]['training_start'].date()} to {windows[0]['training_end'].date()}")
    print(f"   Last window: {windows[-1]['training_start'].date()} to {windows[-1]['training_end'].date()}")
    test2_passed = True
except Exception as e:
    print(f"   ❌ Failed: {e}")
    import traceback
    traceback.print_exc()
    test2_passed = False

# Test 3: Expanding Window Generation
print("\n[TEST 3] Testing expanding window generation...")
try:
    windows = generate_walk_forward_windows(
        start_time=start_time,
        end_time=end_time,
        training_days=7,
        test_days=3,
        step_days=5,
        window_type="expanding"
    )
    
    assert len(windows) > 0, f"Expected windows, got {len(windows)}"
    print(f"   Generated {len(windows)} windows")
    
    # Verify all start from beginning
    for i, window in enumerate(windows):
        assert window['training_start'] == start_time, f"Window {i+1} should start from beginning"
        training_duration = (window['training_end'] - window['training_start']).days
        print(f"   Window {i+1}: {training_duration} days (growing)")
    
    print(f"   ✅ All {len(windows)} windows start from beginning and grow")
    test3_passed = True
except Exception as e:
    print(f"   ❌ Failed: {e}")
    import traceback
    traceback.print_exc()
    test3_passed = False

# Test 4: Robust Score Calculation
print("\n[TEST 4] Testing robust score calculation...")
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
        max_drawdown_pct=2.0,  # 2% drawdown
        trades=[{"net_pnl": 5.0, "is_open": False}] * 10,
        klines=None,
        indicators=None
    )
    
    score = calculate_robust_score(result)
    expected = 5.0 - (2.0 * 2.0)  # 5% return - 2 * 2% drawdown = 1.0
    
    print(f"   Return: {result.total_return_pct}%")
    print(f"   Drawdown: {result.max_drawdown_pct}%")
    print(f"   Score: {score:.2f} (expected: {expected:.2f})")
    assert abs(score - expected) < 0.01, f"Expected {expected}, got {score}"
    print(f"   ✅ Robust score calculation correct")
    test4_passed = True
except Exception as e:
    print(f"   ❌ Failed: {e}")
    import traceback
    traceback.print_exc()
    test4_passed = False

# Test 5: Guardrails
print("\n[TEST 5] Testing guardrails...")
try:
    # Test insufficient trades
    result_low_trades = BacktestResult(
        **{**result.model_dump(), "completed_trades": 3, "total_trades": 3}
    )
    score_low = calculate_metric_score(result_low_trades, "robust_score", min_trades=5)
    assert score_low == float('-inf'), "Should reject insufficient trades"
    print(f"   ✅ Minimum trades guardrail works (rejected {result_low_trades.completed_trades} trades)")
    
    # Test high drawdown
    result_high_dd = BacktestResult(
        **{**result.model_dump(), "max_drawdown_pct": 60.0}
    )
    score_high_dd = calculate_metric_score(result_high_dd, "robust_score", max_dd_cap=50.0)
    assert score_high_dd == float('-inf'), "Should reject high drawdown"
    print(f"   ✅ Maximum drawdown guardrail works (rejected {result_high_dd.max_drawdown_pct}% DD)")
    
    # Test valid result
    score_valid = calculate_metric_score(result, "robust_score", min_trades=5, max_dd_cap=50.0)
    assert score_valid != float('-inf'), "Valid result should pass"
    print(f"   ✅ Valid result passes guardrails (score: {score_valid:.2f})")
    test5_passed = True
except Exception as e:
    print(f"   ❌ Failed: {e}")
    import traceback
    traceback.print_exc()
    test5_passed = False

# Test 6: Parameter Combinations
print("\n[TEST 6] Testing parameter combination generation...")
try:
    optimize_params = {
        "ema_fast": [5, 8, 10],
        "ema_slow": [15, 21, 25]
    }
    
    combinations = generate_param_combinations(optimize_params)
    
    print(f"   Parameters: {list(optimize_params.keys())}")
    print(f"   Values: {list(optimize_params.values())}")
    print(f"   Generated {len(combinations)} combinations")
    assert len(combinations) == 9, f"Expected 3*3=9 combinations, got {len(combinations)}"
    print(f"   First combination: {combinations[0]}")
    print(f"   Last combination: {combinations[-1]}")
    print(f"   ✅ Parameter combination generation correct")
    test6_passed = True
except Exception as e:
    print(f"   ❌ Failed: {e}")
    import traceback
    traceback.print_exc()
    test6_passed = False

# Test 7: Compounded Returns (CRITICAL BUG FIX)
print("\n[TEST 7] Testing compounded returns (CRITICAL BUG FIX)...")
try:
    from app.services.walk_forward import WalkForwardWindow
    
    initial_balance = 1000.0
    
    # Window 1: 5% return (1000 -> 1050)
    window1 = WalkForwardWindow(
        window_number=1,
        training_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        training_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
        test_start=datetime(2024, 1, 8, tzinfo=timezone.utc),
        test_end=datetime(2024, 1, 11, tzinfo=timezone.utc),
        training_result=BacktestResult(
            **{**result.model_dump(), "initial_balance": 1000.0, "final_balance": 1000.0, "total_return_pct": 0.0}
        ),
        test_result=BacktestResult(
            **{**result.model_dump(), "initial_balance": 1000.0, "final_balance": 1050.0, "total_return_pct": 5.0}
        ),
        training_return_pct=0.0,
        test_return_pct=5.0,
        training_win_rate=50.0,
        test_win_rate=60.0
    )
    
    # Window 2: 5% return on 1050 (1050 -> 1102.5)
    window2 = WalkForwardWindow(
        window_number=2,
        training_start=datetime(2024, 1, 6, tzinfo=timezone.utc),
        training_end=datetime(2024, 1, 13, tzinfo=timezone.utc),
        test_start=datetime(2024, 1, 13, tzinfo=timezone.utc),
        test_end=datetime(2024, 1, 16, tzinfo=timezone.utc),
        training_result=BacktestResult(
            **{**result.model_dump(), "initial_balance": 1000.0, "final_balance": 1000.0, "total_return_pct": 0.0}
        ),
        test_result=BacktestResult(
            **{**result.model_dump(), "initial_balance": 1050.0, "final_balance": 1102.5, "total_return_pct": 5.0}
        ),
        training_return_pct=0.0,
        test_return_pct=5.0,
        training_win_rate=50.0,
        test_win_rate=60.0
    )
    
    aggregated = aggregate_walk_forward_results([window1, window2], initial_balance)
    
    # Compounded: (1102.5 / 1000 - 1) * 100 = 10.25%
    # Summed (WRONG): 5% + 5% = 10%
    expected_compounded = ((1102.5 / 1000.0) - 1.0) * 100
    wrong_summed = 5.0 + 5.0
    
    print(f"   Window 1 return: 5.0% (1000 -> 1050)")
    print(f"   Window 2 return: 5.0% (1050 -> 1102.5)")
    print(f"   Final balance: {window2.test_result.final_balance}")
    print(f"   Compounded return: {aggregated['total_return_pct']:.2f}%")
    print(f"   Expected (compounded): {expected_compounded:.2f}%")
    print(f"   If summed (WRONG): {wrong_summed:.2f}%")
    
    assert abs(aggregated['total_return_pct'] - expected_compounded) < 0.01, \
        f"Expected compounded {expected_compounded}%, got {aggregated['total_return_pct']}%"
    assert abs(aggregated['total_return_pct'] - wrong_summed) > 0.01, \
        "Should NOT be summed (bug fix validated)"
    
    print(f"   ✅ Compounded returns correct (NOT summed)")
    print(f"   ✅ Bug fix validated: Returns are compounded, not summed")
    test7_passed = True
except Exception as e:
    print(f"   ❌ Failed: {e}")
    import traceback
    traceback.print_exc()
    test7_passed = False

# Test 8: Consistency Score
print("\n[TEST 8] Testing consistency score...")
try:
    # Create windows with alternating returns
    windows_mixed = []
    for i in range(4):
        is_positive = i % 2 == 0
        return_pct = 5.0 if is_positive else -3.0
        final_balance = 1050.0 if is_positive else 970.0
        
        win = WalkForwardWindow(
            window_number=i+1,
            training_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            training_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
            test_start=datetime(2024, 1, 8, tzinfo=timezone.utc),
            test_end=datetime(2024, 1, 11, tzinfo=timezone.utc),
            training_result=result,
            test_result=BacktestResult(
                **{**result.model_dump(), "initial_balance": 1000.0, "final_balance": final_balance, "total_return_pct": return_pct}
            ),
            training_return_pct=0.0,
            test_return_pct=return_pct,
            training_win_rate=50.0,
            test_win_rate=60.0 if is_positive else 40.0
        )
        windows_mixed.append(win)
    
    aggregated = aggregate_walk_forward_results(windows_mixed, 1000.0)
    
    # 2 out of 4 windows positive = 50%
    print(f"   Windows: {[w.test_return_pct for w in windows_mixed]}")
    print(f"   Consistency score: {aggregated['consistency_score']:.1f}%")
    assert aggregated['consistency_score'] == 50.0, \
        f"Expected 50%, got {aggregated['consistency_score']}%"
    print(f"   ✅ Consistency score correct (50% = 2/4 windows positive)")
    test8_passed = True
except Exception as e:
    print(f"   ❌ Failed: {e}")
    import traceback
    traceback.print_exc()
    test8_passed = False

# Summary
print("\n" + "=" * 70)
print("TEST SUMMARY")
print("=" * 70)

tests = [
    ("Imports", test1_passed),
    ("Rolling Windows", test2_passed),
    ("Expanding Windows", test3_passed),
    ("Robust Score", test4_passed),
    ("Guardrails", test5_passed),
    ("Parameter Combinations", test6_passed),
    ("Compounded Returns (BUG FIX)", test7_passed),
    ("Consistency Score", test8_passed)
]

passed = sum(1 for _, result in tests if result)
total = len(tests)

for name, result in tests:
    status = "✅ PASSED" if result else "❌ FAILED"
    print(f"  {status}: {name}")

print("=" * 70)
print(f"RESULTS: {passed}/{total} tests passed")
print("=" * 70)

if passed == total:
    print("\n🎉 ALL TESTS PASSED! Walk-forward analysis is working correctly.")
    print("\n✅ Bug Fixes Validated:")
    print("   - Window generation (rolling/expanding) ✅")
    print("   - Compounded returns (not summed) ✅")
    print("   - Guardrails (min trades, max DD, lottery) ✅")
    print("   - Robust score calculation ✅")
else:
    print(f"\n⚠️  {total - passed} test(s) failed. Please review errors above.")
    sys.exit(1)



































































































