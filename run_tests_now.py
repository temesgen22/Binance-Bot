"""Run pytest and write results to file."""
import subprocess
import sys
import os
from datetime import datetime

# Change to project directory
project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_root)

output_file = "test_results_run.txt"

print(f"Running walk-forward tests at {datetime.now()}")
print(f"Project root: {project_root}")
print(f"Output file: {output_file}")

# Run pytest
try:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_walk_forward.py", "-v", "--tb=short"],
        capture_output=True,
        text=True,
        timeout=300,  # 5 minute timeout
        cwd=project_root
    )
    
    # Write results
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write(f"WALK-FORWARD TESTS - {datetime.now()}\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Command: python -m pytest tests/test_walk_forward.py -v\n\n")
        f.write("STDOUT:\n")
        f.write("-" * 70 + "\n")
        f.write(result.stdout)
        f.write("\n\nSTDERR:\n")
        f.write("-" * 70 + "\n")
        f.write(result.stderr)
        f.write(f"\n\nExit Code: {result.returncode}\n")
        f.write("=" * 70 + "\n")
    
    # Also print to console
    print("\n" + "=" * 70)
    print("STDOUT:")
    print("-" * 70)
    print(result.stdout)
    if result.stderr:
        print("\nSTDERR:")
        print("-" * 70)
        print(result.stderr)
    print(f"\nExit Code: {result.returncode}")
    print("=" * 70)
    print(f"\nResults saved to: {output_file}")
    
    if result.returncode == 0:
        print("\n✅ ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  Tests failed with exit code {result.returncode}")
    
    sys.exit(result.returncode)
    
except subprocess.TimeoutExpired:
    print("❌ Tests timed out after 5 minutes")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("Tests timed out after 5 minutes\n")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error running tests: {e}")
    import traceback
    traceback.print_exc()
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"Error: {e}\n")
        f.write(traceback.format_exc())
    sys.exit(1)



































































