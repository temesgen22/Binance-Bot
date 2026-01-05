#!/usr/bin/env python
"""Quick test to verify walk-forward works."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

try:
    from datetime import datetime, timezone
    from app.services.walk_forward import generate_walk_forward_windows
    
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 20, tzinfo=timezone.utc)
    windows = generate_walk_forward_windows(start, end, 7, 3, 5, "rolling")
    
    result_file = "quick_test_result.txt"
    with open(result_file, "w") as f:
        f.write(f"SUCCESS: Generated {len(windows)} windows\n")
        if windows:
            f.write(f"First window: {(windows[0]['training_end'] - windows[0]['training_start']).days} days\n")
    
    print(f"SUCCESS: Generated {len(windows)} windows")
    print(f"Result saved to: {result_file}")
    
except Exception as e:
    with open("quick_test_result.txt", "w") as f:
        f.write(f"ERROR: {e}\n")
        import traceback
        f.write(traceback.format_exc())
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)




















































