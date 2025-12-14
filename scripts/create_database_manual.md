# Create Database Manually

Since `psql` is not in your PATH, here are two ways to create the database:

## Option 1: Use Full Path to psql

```powershell
# Replace 18 with your PostgreSQL version if different
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres

# Then in psql prompt:
CREATE DATABASE binance_bot;
\q
```

## Option 2: Add PostgreSQL to PATH (Recommended)

1. **Find PostgreSQL installation:**
   - Usually: `C:\Program Files\PostgreSQL\18\bin`
   - Replace `18` with your version

2. **Add to PATH:**
   - Press `Win + X` → System → Advanced system settings
   - Click "Environment Variables"
   - Under "System variables", find "Path" → Edit
   - Click "New" → Add: `C:\Program Files\PostgreSQL\18\bin`
   - Click OK on all dialogs
   - **Restart PowerShell** (important!)

3. **Verify:**
   ```powershell
   psql --version
   ```

4. **Create database:**
   ```powershell
   createdb -U postgres binance_bot
   ```

## Option 3: Use pgAdmin (GUI)

1. Open **pgAdmin 4** (installed with PostgreSQL)
2. Connect to PostgreSQL server
3. Right-click "Databases" → Create → Database
4. Name: `binance_bot`
5. Click Save


