# Simple script to create PostgreSQL database
# Run this in PowerShell

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Create binance_bot Database" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$psqlPath = "C:\Program Files\PostgreSQL\18\bin\psql.exe"

if (-not (Test-Path $psqlPath)) {
    Write-Host "PostgreSQL not found at: $psqlPath" -ForegroundColor Red
    Write-Host "Please update the path in this script" -ForegroundColor Yellow
    exit 1
}

Write-Host "This will create the 'binance_bot' database." -ForegroundColor Yellow
Write-Host "You will be prompted for the PostgreSQL password." -ForegroundColor Yellow
Write-Host ""

# Create database
Write-Host "Creating database..." -ForegroundColor Green
& $psqlPath -U postgres -c "CREATE DATABASE binance_bot;" 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✓ Database created successfully!" -ForegroundColor Green
} else {
    # Check if it already exists
    $check = & $psqlPath -U postgres -lqt 2>&1 | Select-String "binance_bot"
    if ($check) {
        Write-Host ""
        Write-Host "✓ Database already exists!" -ForegroundColor Yellow
    } else {
        Write-Host ""
        Write-Host "✗ Failed to create database. Please check the error above." -ForegroundColor Red
        Write-Host ""
        Write-Host "You can also create it manually:" -ForegroundColor Yellow
        Write-Host "  1. Open pgAdmin 4" -ForegroundColor White
        Write-Host "  2. Connect to PostgreSQL server" -ForegroundColor White
        Write-Host "  3. Right-click 'Databases' → Create → Database" -ForegroundColor White
        Write-Host "  4. Name: binance_bot" -ForegroundColor White
        exit 1
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Update your .env file:" -ForegroundColor Yellow
Write-Host "   DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/binance_bot" -ForegroundColor White
Write-Host ""
Write-Host "2. Test connection:" -ForegroundColor Yellow
Write-Host "   python scripts/test_database_simple.py" -ForegroundColor White
Write-Host ""


