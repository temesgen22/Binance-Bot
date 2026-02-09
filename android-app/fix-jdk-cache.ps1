# Fix JDK Error - Clean Corrupted Cache
Write-Host "Cleaning corrupted Gradle transform cache..." -ForegroundColor Yellow

# Clean the specific corrupted transform cache
$transformCache = "$env:USERPROFILE\.gradle\caches\transforms-3\a83651df783f4dba4acd526e811c73fb"
if (Test-Path $transformCache) {
    Remove-Item -Recurse -Force $transformCache -ErrorAction SilentlyContinue
    Write-Host "✓ Removed corrupted transform cache" -ForegroundColor Green
} else {
    Write-Host "⚠ Transform cache not found (may have been cleaned already)" -ForegroundColor Yellow
}

# Clean all transform caches (more aggressive)
Write-Host "`nCleaning all transform caches..." -ForegroundColor Cyan
$allTransforms = "$env:USERPROFILE\.gradle\caches\transforms-3"
if (Test-Path $allTransforms) {
    $count = 0
    Get-ChildItem $allTransforms -Directory | ForEach-Object {
        Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue
        $count++
    }
    Write-Host "✓ Removed $count transform cache directories" -ForegroundColor Green
}

# Stop Gradle daemon
Write-Host "`nStopping Gradle daemon..." -ForegroundColor Cyan
if (Test-Path "gradlew.bat") {
    & .\gradlew.bat --stop 2>&1 | Out-Null
    Write-Host "✓ Gradle daemon stopped" -ForegroundColor Green
} else {
    Write-Host "⚠ gradlew.bat not found" -ForegroundColor Yellow
}

Write-Host "`n✓ Cleanup complete!" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. In Android Studio: File → Invalidate Caches → Invalidate and Restart" -ForegroundColor White
Write-Host "2. File → Sync Project with Gradle Files" -ForegroundColor White
Write-Host "3. Build → Rebuild Project" -ForegroundColor White
Write-Host "`nIf it still fails, download Java 17 from: https://adoptium.net/temurin/releases/?version=17" -ForegroundColor Cyan

