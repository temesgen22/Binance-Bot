"""Quick test - minimal output to verify functionality."""
import sys
from datetime import datetime, timezone

try:
    from app.services.walk_forward import generate_walk_forward_windows
    print("IMPORT: OK")
    
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 20, tzinfo=timezone.utc)
    windows = generate_walk_forward_windows(start, end, 7, 3, 5, "rolling")
    print(f"WINDOWS: {len(windows)} generated")
    
    if len(windows) > 0:
        w = windows[0]
        print(f"FIRST: {w['training_start'].date()} to {w['training_end'].date()}")
        duration = (w['training_end'] - w['training_start']).days
        print(f"SIZE: {duration} days (expected 7)")
        if duration == 7:
            print("RESULT: PASS")
        else:
            print("RESULT: FAIL - wrong size")
    else:
        print("RESULT: FAIL - no windows")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)




















































