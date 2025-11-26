# Fix: ModuleNotFoundError for app.core.exceptions

## Problem

Jenkins tests are failing with:
```
ModuleNotFoundError: No module named 'app.core.exceptions'
```

## Root Cause

The `app/core/exceptions.py` file and `__init__.py` files were created locally but not committed to git. When Jenkins checks out the code, these files are missing.

## Solution

You need to commit the following files to git:

1. `app/core/exceptions.py` - The exceptions module
2. `app/core/__init__.py` - Makes app/core a Python package
3. `app/risk/__init__.py` - Makes app/risk a Python package  
4. `app/services/__init__.py` - Makes app/services a Python package

## Steps to Fix

### 1. Verify files exist locally

```bash
# Windows
dir app\core\exceptions.py
dir app\core\__init__.py
dir app\risk\__init__.py
dir app\services\__init__.py

# Linux/Mac
ls -la app/core/exceptions.py
ls -la app/core/__init__.py
ls -la app/risk/__init__.py
ls -la app/services/__init__.py
```

### 2. Check git status

```bash
git status app/core/exceptions.py
git status app/core/__init__.py
git status app/risk/__init__.py
git status app/services/__init__.py
```

### 3. Add files to git

```bash
git add app/core/exceptions.py
git add app/core/__init__.py
git add app/risk/__init__.py
git add app/services/__init__.py
```

### 4. Commit and push

```bash
git commit -m "Add exceptions module and missing __init__.py files for Python packages"
git push
```

### 5. Re-run Jenkins pipeline

After pushing, Jenkins will automatically run the pipeline (if configured), or you can manually trigger it.

## Verification

After committing and pushing, you can verify the files are in git:

```bash
git ls-files | grep "app/core/exceptions.py"
git ls-files | grep "app/core/__init__.py"
```

All files should be listed.

## Why These Files Are Needed

- **`exceptions.py`**: Contains all custom exception classes used throughout the application
- **`__init__.py` files**: Required by Python to recognize directories as packages. Without them, imports like `from app.core.exceptions import ...` fail.

## Expected Result

After committing and pushing, Jenkins tests should pass and you should see:
- All test files collect successfully (no import errors)
- Tests run and complete

