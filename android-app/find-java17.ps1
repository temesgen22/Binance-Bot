# Find Java 17 Installation
Write-Host "Searching for Java 17..." -ForegroundColor Cyan

$locations = @(
    "C:\Program Files\Eclipse Adoptium",
    "C:\Program Files\Java",
    "C:\Program Files (x86)\Java"
)

$found = $false

foreach ($location in $locations) {
    if (Test-Path $location) {
        Write-Host "`nChecking: $location" -ForegroundColor Yellow
        Get-ChildItem $location -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $javaExe = Join-Path $_.FullName "bin\java.exe"
            if (Test-Path $javaExe) {
                $version = & $javaExe -version 2>&1 | Select-String "version"
                if ($version -match "17") {
                    Write-Host "`nFOUND Java 17!" -ForegroundColor Green
                    Write-Host "  Path: $($_.FullName)" -ForegroundColor Yellow
                    Write-Host "  Version: $version" -ForegroundColor Yellow
                    $gradlePath = $_.FullName -replace '\\', '/'
                    Write-Host "`nAdd this to gradle.properties:" -ForegroundColor Cyan
                    Write-Host "org.gradle.java.home=$gradlePath" -ForegroundColor White
                    $found = $true
                }
            }
        }
    }
}

if (-not $found) {
    Write-Host "`nJava 17 not found automatically." -ForegroundColor Yellow
    Write-Host "`nPlease provide the Java 17 installation path manually." -ForegroundColor Yellow
    Write-Host "Common locations:" -ForegroundColor Cyan
    Write-Host "  - C:\Program Files\Eclipse Adoptium\jdk-17.x.x-hotspot" -ForegroundColor White
    Write-Host "  - C:\Program Files\Java\jdk-17" -ForegroundColor White
}
