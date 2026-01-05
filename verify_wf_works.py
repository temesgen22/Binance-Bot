"""Simple verification that walk-forward functions work."""
import sys
from datetime import datetime, timezone

# Test imports
try:
    from app.services.walk_forward import generate_walk_forward_windows
    print("PASS: Imports work")
except Exception as e:
    print(f"FAIL: Imports - {e}")
    sys.exit(1)

# Test window generation
try:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 20, tzinfo=timezone.utc)
    windows = generate_walk_forward_windows(start, end, 7, 3, 5, "rolling")
    
    if len(windows) == 0:
        print("FAIL: No windows generated")
        sys.exit(1)
    
    # Check first window
    w = windows[0]
    duration = (w['training_end'] - w['training_start']).days
    
    if duration != 7:
        print(f"FAIL: Window size is {duration}, expected 7")
        sys.exit(1)
    
    print(f"PASS: Generated {len(windows)} windows")
    print(f"PASS: First window is {duration} days (correct)")
    print(f"PASS: Window generation works correctly")
    
except Exception as e:
    print(f"FAIL: Window generation - {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test expanding
try:
    windows = generate_walk_forward_windows(start, end, 7, 3, 5, "expanding")
    if len(windows) == 0:
        print("FAIL: No expanding windows")
        sys.exit(1)
    
    if windows[0]['training_start'] != start:
        print("FAIL: Expanding windows don't start from beginning")
        sys.exit(1)
    
    print("PASS: Expanding windows work correctly")
    
except Exception as e:
    print(f"FAIL: Expanding windows - {e}")
    sys.exit(1)

print("\n✅ ALL BASIC TESTS PASSED - Walk-forward functionality is working!")

















































