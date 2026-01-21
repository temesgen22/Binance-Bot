"""Test walk-forward and write results to file."""
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results = []
results.append("=" * 70)
results.append("WALK-FORWARD ANALYSIS TEST RESULTS")
results.append("=" * 70)

# Test 1: Imports
results.append("\n[1] Testing imports...")
try:
    from app.services.walk_forward import (
        generate_walk_forward_windows,
        calculate_robust_score,
        aggregate_walk_forward_results,
        calculate_metric_score,
        generate_param_combinations
    )
    from app.api.routes.backtesting import BacktestResult
    results.append("✅ Imports: SUCCESS")
except Exception as e:
    results.append(f"❌ Imports: FAILED - {e}")
    with open("test_wf_results.txt", "w") as f:
        f.write("\n".join(results))
    sys.exit(1)

# Test 2: Rolling Windows
results.append("\n[2] Testing rolling windows...")
try:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 20, tzinfo=timezone.utc)
    windows = generate_walk_forward_windows(start, end, 7, 3, 5, "rolling")
    assert len(windows) > 0
    for w in windows:
        duration = (w['training_end'] - w['training_start']).days
        assert duration == 7
    results.append(f"✅ Rolling windows: SUCCESS ({len(windows)} windows, all 7 days)")
except Exception as e:
    results.append(f"❌ Rolling windows: FAILED - {e}")

# Test 3: Expanding Windows
results.append("\n[3] Testing expanding windows...")
try:
    windows = generate_walk_forward_windows(start, end, 7, 3, 5, "expanding")
    assert len(windows) > 0
    for w in windows:
        assert w['training_start'] == start
    results.append(f"✅ Expanding windows: SUCCESS ({len(windows)} windows)")
except Exception as e:
    results.append(f"❌ Expanding windows: FAILED - {e}")

# Test 4: Robust Score
results.append("\n[4] Testing robust score...")
try:
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
    expected = 5.0 - (2.0 * 2.0)
    assert abs(score - expected) < 0.01
    results.append(f"✅ Robust score: SUCCESS (score={score:.2f}, expected={expected:.2f})")
except Exception as e:
    results.append(f"❌ Robust score: FAILED - {e}")

# Test 5: Guardrails
results.append("\n[5] Testing guardrails...")
try:
    result_low = BacktestResult(**{**result.model_dump(), "completed_trades": 3})
    score = calculate_metric_score(result_low, "robust_score", min_trades=5)
    assert score == float('-inf')
    results.append("✅ Guardrails: SUCCESS (min trades enforced)")
except Exception as e:
    results.append(f"❌ Guardrails: FAILED - {e}")

# Test 6: Parameter Combinations
results.append("\n[6] Testing parameter combinations...")
try:
    params = {"ema_fast": [5, 8], "ema_slow": [15, 21]}
    combos = generate_param_combinations(params)
    assert len(combos) == 4
    results.append(f"✅ Parameter combinations: SUCCESS ({len(combos)} combinations)")
except Exception as e:
    results.append(f"❌ Parameter combinations: FAILED - {e}")

# Test 7: Compounded Returns
results.append("\n[7] Testing compounded returns (BUG FIX)...")
try:
    from app.services.walk_forward import WalkForwardWindow
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
    expected = ((1102.5 / 1000.0) - 1.0) * 100
    assert abs(agg['total_return_pct'] - expected) < 0.01
    results.append(f"✅ Compounded returns: SUCCESS ({agg['total_return_pct']:.2f}% compounded, not 10% summed)")
except Exception as e:
    results.append(f"❌ Compounded returns: FAILED - {e}")
    import traceback
    results.append(traceback.format_exc())

# Summary
results.append("\n" + "=" * 70)
passed = sum(1 for r in results if "✅" in r)
total = 7
results.append(f"SUMMARY: {passed}/{total} tests passed")
results.append("=" * 70)

# Write to file
with open("test_wf_results.txt", "w") as f:
    f.write("\n".join(results))

# Also print
print("\n".join(results))

if passed == total:
    print("\n🎉 ALL TESTS PASSED!")
else:
    print(f"\n⚠️ {total - passed} test(s) failed")



































































































