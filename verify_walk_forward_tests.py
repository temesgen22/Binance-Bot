"""
Quick verification of walk-forward test functionality.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results = []

def test(name, func):
    """Run a test and record result."""
    try:
        func()
        results.append(f"✅ {name}: PASSED")
        return True
    except Exception as e:
        results.append(f"❌ {name}: FAILED - {e}")
        import traceback
        results.append(traceback.format_exc())
        return False

# Test 1: Imports
def test_imports():
    from app.services.walk_forward import (
        generate_walk_forward_windows,
        calculate_robust_score,
        aggregate_walk_forward_results
    )
    from app.api.routes.backtesting import BacktestResult

test("Imports", test_imports)

# Test 2: Window generation - rolling
def test_rolling_windows():
    from datetime import datetime, timezone
    from app.services.walk_forward import generate_walk_forward_windows
    
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
    
    assert len(windows) > 0, "Should generate windows"
    for window in windows:
        duration = (window['training_end'] - window['training_start']).days
        assert duration == 7, f"Expected 7 days, got {duration}"

test("Rolling Windows", test_rolling_windows)

# Test 3: Window generation - expanding
def test_expanding_windows():
    from datetime import datetime, timezone
    from app.services.walk_forward import generate_walk_forward_windows
    
    start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end_time = datetime(2024, 1, 20, tzinfo=timezone.utc)
    
    windows = generate_walk_forward_windows(
        start_time=start_time,
        end_time=end_time,
        training_days=7,
        test_days=3,
        step_days=5,
        window_type="expanding"
    )
    
    assert len(windows) > 0, "Should generate windows"
    for window in windows:
        assert window['training_start'] == start_time, "Should start from beginning"

test("Expanding Windows", test_expanding_windows)

# Test 4: Robust score
def test_robust_score():
    from datetime import datetime, timedelta, timezone
    from app.services.walk_forward import calculate_robust_score
    from app.api.routes.backtesting import BacktestResult
    
    result = BacktestResult(
        symbol="BTCUSDT",
        strategy_type="scalping",
        start_time=datetime.now(timezone.utc) - timedelta(days=30),
        end_time=datetime.now(timezone.utc),
        initial_balance=1000.0,
        final_balance=1050.0,
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
        trades=[{"net_pnl": 5.0}] * 10,
        klines=None,
        indicators=None
    )
    
    score = calculate_robust_score(result)
    expected = 5.0 - (2.0 * 2.0)  # 1.0
    assert abs(score - expected) < 0.01, f"Expected {expected}, got {score}"

test("Robust Score", test_robust_score)

# Test 5: Parameter combinations
def test_param_combinations():
    from app.services.walk_forward import generate_param_combinations
    
    optimize_params = {"ema_fast": [5, 8], "ema_slow": [15, 21]}
    combinations = generate_param_combinations(optimize_params)
    
    assert len(combinations) == 4, f"Expected 4, got {len(combinations)}"

test("Parameter Combinations", test_param_combinations)

# Test 6: Compounded returns
def test_compounded_returns():
    from datetime import datetime, timezone
    from app.services.walk_forward import aggregate_walk_forward_results, WalkForwardWindow
    from app.api.routes.backtesting import BacktestResult
    
    # Create two windows with 5% return each
    window1 = WalkForwardWindow(
        window_number=1,
        training_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        training_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
        test_start=datetime(2024, 1, 8, tzinfo=timezone.utc),
        test_end=datetime(2024, 1, 11, tzinfo=timezone.utc),
        training_result=BacktestResult(
            symbol="BTCUSDT", strategy_type="scalping",
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 8, tzinfo=timezone.utc),
            initial_balance=1000.0, final_balance=1000.0,
            total_pnl=0.0, total_return_pct=0.0, total_trades=0,
            completed_trades=0, open_trades=0, winning_trades=0,
            losing_trades=0, win_rate=0.0, total_fees=0.0,
            avg_profit_per_trade=0.0, largest_win=0.0, largest_loss=0.0,
            max_drawdown=0.0, max_drawdown_pct=0.0, trades=[], klines=None, indicators=None
        ),
        test_result=BacktestResult(
            symbol="BTCUSDT", strategy_type="scalping",
            start_time=datetime(2024, 1, 8, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 11, tzinfo=timezone.utc),
            initial_balance=1000.0, final_balance=1050.0,
            total_pnl=50.0, total_return_pct=5.0, total_trades=10,
            completed_trades=10, open_trades=0, winning_trades=6,
            losing_trades=4, win_rate=60.0, total_fees=3.0,
            avg_profit_per_trade=5.0, largest_win=10.0, largest_loss=-5.0,
            max_drawdown=20.0, max_drawdown_pct=2.0, trades=[], klines=None, indicators=None
        ),
        training_return_pct=0.0, test_return_pct=5.0,
        training_win_rate=50.0, test_win_rate=60.0
    )
    
    window2 = WalkForwardWindow(
        window_number=2,
        training_start=datetime(2024, 1, 6, tzinfo=timezone.utc),
        training_end=datetime(2024, 1, 13, tzinfo=timezone.utc),
        test_start=datetime(2024, 1, 13, tzinfo=timezone.utc),
        test_end=datetime(2024, 1, 16, tzinfo=timezone.utc),
        training_result=window1.training_result,
        test_result=BacktestResult(
            symbol="BTCUSDT", strategy_type="scalping",
            start_time=datetime(2024, 1, 13, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 16, tzinfo=timezone.utc),
            initial_balance=1050.0, final_balance=1102.5,
            total_pnl=52.5, total_return_pct=5.0, total_trades=10,
            completed_trades=10, open_trades=0, winning_trades=6,
            losing_trades=4, win_rate=60.0, total_fees=3.0,
            avg_profit_per_trade=5.25, largest_win=10.0, largest_loss=-5.0,
            max_drawdown=20.0, max_drawdown_pct=2.0, trades=[], klines=None, indicators=None
        ),
        training_return_pct=0.0, test_return_pct=5.0,
        training_win_rate=50.0, test_win_rate=60.0
    )
    
    aggregated = aggregate_walk_forward_results([window1, window2], 1000.0)
    
    # Should be compounded: (1102.5 / 1000 - 1) * 100 = 10.25%
    expected = ((1102.5 / 1000.0) - 1.0) * 100
    assert abs(aggregated['total_return_pct'] - expected) < 0.01, \
        f"Expected {expected}%, got {aggregated['total_return_pct']}%"

test("Compounded Returns", test_compounded_returns)

# Print results
print("\n" + "=" * 60)
print("Walk-Forward Test Verification Results")
print("=" * 60)
for result in results:
    print(result)
print("=" * 60)

# Count passes
passed = sum(1 for r in results if "✅" in r)
total = len([r for r in results if "✅" in r or "❌" in r])
print(f"\nSummary: {passed}/{total} tests passed")

if passed == total:
    print("🎉 All tests passed!")
    sys.exit(0)
else:
    print("⚠️  Some tests failed")
    sys.exit(1)





























































