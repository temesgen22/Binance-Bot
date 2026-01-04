"""Execute tests and write results."""
import sys
import os
import subprocess
from pathlib import Path

os.chdir(Path(__file__).parent)

output_path = Path("test_execution_results.txt")

print("Starting test execution...", file=sys.stderr)
print(f"Working directory: {os.getcwd()}", file=sys.stderr)

try:
    # Run pytest
    proc = subprocess.Popen(
        [sys.executable, "-m", "pytest", "tests/test_walk_forward.py", "-v", "--tb=short"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=os.getcwd()
    )
    
    stdout, stderr = proc.communicate(timeout=300)
    
    # Write to file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=== PYTEST OUTPUT ===\n\n")
        f.write(stdout)
        if stderr:
            f.write("\n\n=== STDERR ===\n\n")
            f.write(stderr)
        f.write(f"\n\n=== EXIT CODE: {proc.returncode} ===\n")
    
    # Also print
    print(stdout, file=sys.stderr)
    if stderr:
        print("\nSTDERR:", file=sys.stderr)
        print(stderr, file=sys.stderr)
    print(f"\nExit code: {proc.returncode}", file=sys.stderr)
    print(f"Results written to: {output_path}", file=sys.stderr)
    
    sys.exit(proc.returncode)
    
except Exception as e:
    error_msg = f"Error: {e}\n"
    print(error_msg, file=sys.stderr)
    with open(output_path, "w") as f:
        f.write(error_msg)
    sys.exit(1)














































