# Quick script to set up DATABASE_URL in .env file

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Configure Database URL in .env" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$envFile = ".env"
$envExample = "env.example"

# Check if .env exists
if (-not (Test-Path $envFile)) {
    Write-Host ".env file not found. Creating from env.example..." -ForegroundColor Yellow
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host "✓ Created .env from env.example" -ForegroundColor Green
    } else {
        Write-Host "✗ env.example not found. Please create .env manually." -ForegroundColor Red
        exit 1
    }
}

# Get PostgreSQL password
Write-Host "Enter your PostgreSQL password (for user 'postgres'):" -ForegroundColor Yellow
$password = Read-Host -AsSecureString
$passwordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password)
)

# Create DATABASE_URL
$databaseUrl = "postgresql://postgres:$passwordPlain@localhost:5432/binance_bot"

# Read .env file
$content = Get-Content $envFile -Raw

# Check if DATABASE_URL already exists
if ($content -match "DATABASE_URL=") {
    Write-Host ""
    Write-Host "DATABASE_URL already exists in .env" -ForegroundColor Yellow
    Write-Host "Updating it..." -ForegroundColor Yellow
    
    # Replace existing DATABASE_URL
    $content = $content -replace "DATABASE_URL=.*", "DATABASE_URL=$databaseUrl"
} else {
    Write-Host ""
    Write-Host "Adding DATABASE_URL to .env..." -ForegroundColor Yellow
    
    # Add DATABASE_URL if it doesn't exist
    if (-not $content.EndsWith("`n")) {
        $content += "`n"
    }
    $content += "`n# PostgreSQL Database Configuration`n"
    $content += "DATABASE_URL=$databaseUrl`n"
}

# Write back to file
Set-Content -Path $envFile -Value $content -NoNewline

Write-Host "✓ Updated .env file" -ForegroundColor Green
Write-Host ""
Write-Host "Next step: Test the connection" -ForegroundColor Cyan
Write-Host "  python scripts/test_connection_quick.py" -ForegroundColor White
Write-Host ""


