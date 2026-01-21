"""Run walk-forward tests and save output."""
import subprocess
import sys
import os
from pathlib import Path

os.chdir(Path(__file__).parent)

print("Running walk-forward tests...")
print("=" * 70)

try:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_walk_forward.py", "-v", "--tb=short"],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=os.getcwd()
    )
    
    output_file = Path("test_results_final.txt")
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("WALK-FORWARD TESTS - FINAL RESULTS\n")
        f.write("=" * 70 + "\n\n")
        f.write(result.stdout)
        if result.stderr:
            f.write("\n\nSTDERR:\n")
            f.write("-" * 70 + "\n")
            f.write(result.stderr)
        f.write(f"\n\nExit Code: {result.returncode}\n")
        f.write("=" * 70 + "\n")
    
    # Print to console
    print(result.stdout)
    if result.stderr:
        print("\nSTDERR:")
        print(result.stderr)
    print(f"\nExit Code: {result.returncode}")
    print(f"\nResults saved to: {output_file}")
    
    if result.returncode == 0:
        print("\n✅ ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  Some tests failed (exit code: {result.returncode})")
    
    sys.exit(result.returncode)
    
except subprocess.TimeoutExpired:
    print("❌ Tests timed out after 5 minutes")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)




































































































