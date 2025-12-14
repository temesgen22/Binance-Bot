# PowerShell script to create PostgreSQL database
# This uses the full path to psql to avoid PATH issues

# Default PostgreSQL installation path (adjust if different)
$postgresVersion = "18"
$postgresPath = "C:\Program Files\PostgreSQL\$postgresVersion\bin"

# Check if psql exists
$psqlPath = Join-Path $postgresPath "psql.exe"
if (-not (Test-Path $psqlPath)) {
    Write-Host "PostgreSQL not found at: $psqlPath" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please update the script with your PostgreSQL installation path" -ForegroundColor Yellow
    Write-Host "Common locations:" -ForegroundColor Yellow
    Write-Host "  C:\Program Files\PostgreSQL\18\bin\psql.exe" -ForegroundColor Cyan
    Write-Host "  C:\Program Files\PostgreSQL\16\bin\psql.exe" -ForegroundColor Cyan
    Write-Host "  C:\Program Files\PostgreSQL\15\bin\psql.exe" -ForegroundColor Cyan
    exit 1
}

Write-Host "Creating database 'binance_bot'..." -ForegroundColor Green
Write-Host ""

# Set environment variable for password prompt
$env:PGPASSWORD = Read-Host "Enter PostgreSQL password for user 'postgres'" -AsSecureString | ConvertFrom-SecureString -AsPlainText

# Create database
& $psqlPath -U postgres -c "CREATE DATABASE binance_bot;" 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✓ Database 'binance_bot' created successfully!" -ForegroundColor Green
} elseif ($LASTEXITCODE -eq 1) {
    # Check if database already exists
    $checkResult = & $psqlPath -U postgres -lqt 2>&1 | Select-String "binance_bot"
    if ($checkResult) {
        Write-Host ""
        Write-Host "✓ Database 'binance_bot' already exists" -ForegroundColor Yellow
    } else {
        Write-Host ""
        Write-Host "✗ Failed to create database. Check the error above." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host ""
    Write-Host "✗ Error creating database. Exit code: $LASTEXITCODE" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Update your .env file with DATABASE_URL" -ForegroundColor White
Write-Host "  2. Run: python scripts/test_database_simple.py" -ForegroundColor White


