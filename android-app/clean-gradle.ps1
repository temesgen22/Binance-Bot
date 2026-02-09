# Gradle Cleanup Script
# Run this script to clean all Gradle caches and rebuild

Write-Host "Cleaning Gradle cache and build artifacts..." -ForegroundColor Yellow

# Stop Gradle daemon
Write-Host "`n1. Stopping Gradle daemon..." -ForegroundColor Cyan
if (Test-Path "gradlew.bat") {
    & .\gradlew.bat --stop 2>&1 | Out-Null
    Write-Host "   ✓ Gradle daemon stopped" -ForegroundColor Green
} else {
    Write-Host "   ⚠ gradlew.bat not found, skipping" -ForegroundColor Yellow
}

# Clean local build directories
Write-Host "`n2. Cleaning build directories..." -ForegroundColor Cyan
$dirsToClean = @(".gradle", "app\build", "build")
foreach ($dir in $dirsToClean) {
    if (Test-Path $dir) {
        Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
        Write-Host "   ✓ Removed $dir" -ForegroundColor Green
    }
}

# Clean Gradle user cache (optional - uncomment if needed)
Write-Host "`n3. Gradle user cache..." -ForegroundColor Cyan
$gradleUserHome = "$env:USERPROFILE\.gradle"
$cachesDir = "$gradleUserHome\caches"
if (Test-Path $cachesDir) {
    Write-Host "   ⚠ Gradle cache found at: $cachesDir" -ForegroundColor Yellow
    Write-Host "   To clean it, run: Remove-Item -Recurse -Force `"$cachesDir`"" -ForegroundColor Gray
    Write-Host "   (This will re-download all dependencies)" -ForegroundColor Gray
} else {
    Write-Host "   ✓ No Gradle cache found" -ForegroundColor Green
}

Write-Host "`n✓ Cleanup complete!" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. Open Android Studio" -ForegroundColor White
Write-Host "2. File → Sync Project with Gradle Files" -ForegroundColor White
Write-Host "3. Build → Rebuild Project" -ForegroundColor White
