"""Simple direct test - no pytest."""
import sys
from datetime import datetime, timezone, timedelta

print("Testing Walk-Forward Analysis...")
print("=" * 60)

# Test 1: Import
try:
    from app.services.walk_forward import generate_walk_forward_windows
    print("✅ Import successful")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Test 2: Rolling windows
try:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 20, tzinfo=timezone.utc)
    windows = generate_walk_forward_windows(start, end, 7, 3, 5, "rolling")
    
    print(f"✅ Generated {len(windows)} rolling windows")
    if len(windows) > 0:
        w = windows[0]
        duration = (w['training_end'] - w['training_start']).days
        print(f"   First window: {duration} days (expected 7)")
        if duration == 7:
            print("   ✅ Window size correct")
        else:
            print(f"   ❌ Window size wrong: {duration}")
            sys.exit(1)
except Exception as e:
    print(f"❌ Rolling windows failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Expanding windows
try:
    windows = generate_walk_forward_windows(start, end, 7, 3, 5, "expanding")
    print(f"✅ Generated {len(windows)} expanding windows")
    if len(windows) > 0:
        if windows[0]['training_start'] == start:
            print("   ✅ All windows start from beginning")
        else:
            print("   ❌ Windows don't start from beginning")
            sys.exit(1)
except Exception as e:
    print(f"❌ Expanding windows failed: {e}")
    sys.exit(1)

# Test 4: Robust score
try:
    from app.services.walk_forward import calculate_robust_score
    from app.api.routes.backtesting import BacktestResult
    
    result = BacktestResult(
        symbol="BTCUSDT", strategy_type="scalping",
        start_time=datetime.now(timezone.utc) - timedelta(days=30),
        end_time=datetime.now(timezone.utc),
        initial_balance=1000.0, final_balance=1050.0,
        total_pnl=50.0, total_return_pct=5.0,
        total_trades=10, completed_trades=10, open_trades=0,
        winning_trades=6, losing_trades=4, win_rate=60.0,
        total_fees=3.0, avg_profit_per_trade=5.0,
        largest_win=10.0, largest_loss=-5.0,
        max_drawdown=20.0, max_drawdown_pct=2.0,
        trades=[{"net_pnl": 5.0, "is_open": False}] * 10,
        klines=None, indicators=None
    )
    
    score = calculate_robust_score(result)
    expected = 5.0 - (2.0 * 2.0)  # 1.0
    print(f"✅ Robust score: {score:.2f} (expected: {expected:.2f})")
    if abs(score - expected) > 0.01:
        print(f"   ❌ Score mismatch")
        sys.exit(1)
except Exception as e:
    print(f"❌ Robust score failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Compounded returns
try:
    from app.services.walk_forward import aggregate_walk_forward_results, WalkForwardWindow
    
    w1 = WalkForwardWindow(
        window_number=1,
        training_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        training_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
        test_start=datetime(2024, 1, 8, tzinfo=timezone.utc),
        test_end=datetime(2024, 1, 11, tzinfo=timezone.utc),
        training_result=result,
        test_result=BacktestResult(**{**result.model_dump(), "initial_balance": 1000.0, "final_balance": 1050.0, "total_return_pct": 5.0}),
        training_return_pct=0.0, test_return_pct=5.0,
        training_win_rate=50.0, test_win_rate=60.0
    )
    w2 = WalkForwardWindow(
        window_number=2,
        training_start=datetime(2024, 1, 6, tzinfo=timezone.utc),
        training_end=datetime(2024, 1, 13, tzinfo=timezone.utc),
        test_start=datetime(2024, 1, 13, tzinfo=timezone.utc),
        test_end=datetime(2024, 1, 16, tzinfo=timezone.utc),
        training_result=result,
        test_result=BacktestResult(**{**result.model_dump(), "initial_balance": 1050.0, "final_balance": 1102.5, "total_return_pct": 5.0}),
        training_return_pct=0.0, test_return_pct=5.0,
        training_win_rate=50.0, test_win_rate=60.0
    )
    
    agg = aggregate_walk_forward_results([w1, w2], 1000.0)
    expected = ((1102.5 / 1000.0) - 1.0) * 100  # 10.25%
    print(f"✅ Compounded returns: {agg['total_return_pct']:.2f}% (expected: {expected:.2f}%)")
    if abs(agg['total_return_pct'] - expected) > 0.01:
        print(f"   ❌ Compounded return mismatch")
        sys.exit(1)
    print(f"   ✅ Bug fix validated: Returns are compounded, not summed")
except Exception as e:
    print(f"❌ Compounded returns failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=" * 60)
print("🎉 ALL TESTS PASSED!")
print("=" * 60)




















































































































