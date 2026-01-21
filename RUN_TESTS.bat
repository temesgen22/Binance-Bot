@echo off
echo ========================================
echo Running Walk-Forward Tests
echo ========================================
echo.

cd /d "%~dp0"

echo Running: python -m pytest tests/test_walk_forward.py -v
echo.

python -m pytest tests/test_walk_forward.py -v

echo.
echo ========================================
echo Test execution complete!
echo ========================================
pause





































































































