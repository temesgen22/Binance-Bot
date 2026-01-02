"""Run pytest for walk-forward tests and save output."""
import subprocess
import sys
import os

# Change to project directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Running walk-forward tests with pytest...")
print("=" * 70)

# Run pytest and capture output
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_walk_forward.py", "-v", "--tb=short"],
    capture_output=True,
    text=True,
    cwd=os.getcwd()
)

# Print output
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

# Write to file
with open("pytest_wf_output.txt", "w") as f:
    f.write("=" * 70 + "\n")
    f.write("WALK-FORWARD TESTS OUTPUT\n")
    f.write("=" * 70 + "\n\n")
    f.write(result.stdout)
    if result.stderr:
        f.write("\n\nSTDERR:\n")
        f.write(result.stderr)
    f.write(f"\n\nExit code: {result.returncode}\n")

print("=" * 70)
print(f"Tests completed with exit code: {result.returncode}")
print("Output saved to: pytest_wf_output.txt")

if result.returncode == 0:
    print("✅ ALL TESTS PASSED!")
else:
    print("⚠️  Some tests failed. Check output above or pytest_wf_output.txt")

sys.exit(result.returncode)




































