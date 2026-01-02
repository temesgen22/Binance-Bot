"""Test that circular import is fixed."""
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

result_file = "circular_import_test_result.txt"

try:
    print("Testing imports...")
    
    # Test 1: Import walk_forward
    from app.services.walk_forward import generate_walk_forward_windows
    print("✅ Imported walk_forward")
    
    # Test 2: Import backtesting (this was causing the circular import)
    from app.api.routes.backtesting import router
    print("✅ Imported backtesting router")
    
    # Test 3: Import both together
    from app.services.walk_forward import WalkForwardRequest, WalkForwardResult
    from app.api.routes.backtesting import router as backtesting_router
    print("✅ Imported both modules together")
    
    # Test 4: Try to use the function
    from datetime import datetime, timezone
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 20, tzinfo=timezone.utc)
    windows = generate_walk_forward_windows(start, end, 7, 3, 5, "rolling")
    print(f"✅ Generated {len(windows)} windows")
    
    result = "SUCCESS: All imports work! Circular import is fixed.\n"
    result += f"Generated {len(windows)} windows successfully.\n"
    
    with open(result_file, "w") as f:
        f.write(result)
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED - Circular import is FIXED!")
    print("=" * 60)
    
except ImportError as e:
    error_msg = f"FAILED: Import error - {e}\n"
    print(f"\n❌ {error_msg}")
    with open(result_file, "w") as f:
        f.write(error_msg)
        import traceback
        f.write(traceback.format_exc())
    sys.exit(1)
except Exception as e:
    error_msg = f"FAILED: {e}\n"
    print(f"\n❌ {error_msg}")
    with open(result_file, "w") as f:
        f.write(error_msg)
        import traceback
        f.write(traceback.format_exc())
    sys.exit(1)






































