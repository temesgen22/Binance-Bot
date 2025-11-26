# Troubleshooting Log Viewer GUI

## Issue: Root URL (/) Not Loading GUI

If `http://127.0.0.1:8000/` doesn't work but `http://127.0.0.1:8000/docs` does, follow these steps:

### 1. Verify Static File Exists

Check if the HTML file exists:
```bash
# Windows
dir app\static\index.html

# Linux/Mac
ls -la app/static/index.html
```

### 2. Check Server Logs

When you start the server, check for any error messages:
```bash
uvicorn app.main:app --reload
```

Look for errors related to static files or FileResponse.

### 3. Verify Server Startup Method

Make sure you're starting the server correctly:

**For development:**
```bash
uvicorn app.main:app --reload
```

**For production/Docker:**
```bash
uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

The `--factory` flag is important when using Docker!

### 4. Test Direct Access

Try accessing the static file directly:
```
http://127.0.0.1:8000/static/index.html
```

If this works but `/` doesn't, there's a route issue.

### 5. Check Route Order

The root route (`/`) should be defined before API routers. The code in `app/main.py` should have:

```python
# Root route first
@app.get("/")
async def root():
    ...

# Then static mount
app.mount("/static", ...)

# Then API routers
app.include_router(...)
```

### 6. Clear Browser Cache

Sometimes browsers cache redirects. Try:
- Hard refresh: `Ctrl+F5` (Windows) or `Cmd+Shift+R` (Mac)
- Open in incognito/private mode
- Clear browser cache

### 7. Verify File Path

The server looks for the file at:
- **Development**: `app/static/index.html` (relative to project root)
- **Docker**: `/app/app/static/index.html` (inside container)

Check the actual path in the error response if you see an error message.

### 8. Test with curl

Test the endpoint directly:
```bash
curl http://127.0.0.1:8000/
```

You should see HTML content, not a JSON error.

### 9. Common Issues and Fixes

#### Issue: "Log Viewer GUI not found" message

**Cause**: The `app/static/index.html` file doesn't exist or isn't in the expected location.

**Fix**: 
1. Verify the file exists: `app/static/index.html`
2. If running in Docker, ensure the file is copied into the image:
   ```dockerfile
   COPY . ${APP_HOME}
   ```
3. Check file permissions

#### Issue: 404 Not Found

**Cause**: Route not registered or route order issue.

**Fix**: 
1. Ensure the root route is defined in `create_app()` function
2. Verify route is registered before other routes
3. Restart the server

#### Issue: Blank page or JavaScript errors

**Cause**: HTML loads but JavaScript fails to fetch API endpoints.

**Fix**:
1. Open browser developer console (F12)
2. Check for JavaScript errors
3. Verify API endpoints are accessible: `http://127.0.0.1:8000/logs/`
4. Check CORS if accessing from different origin

#### Issue: Works locally but not in Docker

**Cause**: File path or permissions issue in container.

**Fix**:
1. Verify file is copied in Dockerfile:
   ```dockerfile
   COPY . ${APP_HOME}
   ```
2. Check file exists in container:
   ```bash
   docker exec binance-bot-api ls -la /app/app/static/
   ```
3. Verify working directory in Dockerfile is correct

### 10. Debug Mode

To see what's happening, you can temporarily add logging:

```python
@app.get("/")
async def root():
    from loguru import logger
    logger.info(f"Static dir: {static_dir}, exists: {static_dir.exists()}")
    logger.info(f"Index path: {index_path}, exists: {index_path.exists()}")
    ...
```

### 11. Verify FastAPI Version

Make sure you have the correct FastAPI version:
```bash
pip show fastapi
```

Should be `>= 0.110.0` for proper FileResponse support.

### Quick Fix Checklist

- [ ] File exists at `app/static/index.html`
- [ ] Server restarted after code changes
- [ ] Using correct startup command (with `--factory` if using Docker)
- [ ] No errors in server logs
- [ ] Browser cache cleared
- [ ] Direct static access works: `/static/index.html`
- [ ] API endpoints work: `/docs`, `/health`

If all else fails, try accessing directly:
```
http://127.0.0.1:8000/static/index.html
```

This bypasses the root route and accesses the file directly.

