# Fix Jenkins Docker Permissions Script
# Run this script to fix Docker permissions in Jenkins container

Write-Host "Fixing Jenkins Docker permissions..." -ForegroundColor Yellow

# Check if Jenkins container exists
$jenkinsExists = docker ps -a --filter "name=jenkins" --format "{{.Names}}"
if (-not $jenkinsExists) {
    Write-Host "Jenkins container not found. Please start Jenkins first." -ForegroundColor Red
    exit 1
}

Write-Host "Stopping Jenkins container..." -ForegroundColor Yellow
docker stop jenkins

Write-Host "Fixing Docker socket permissions and installing Python venv..." -ForegroundColor Yellow
# Fix permissions and install Python venv inside container
docker exec -u root jenkins bash -c @"
apt-get update -qq
apt-get install -y python3-venv docker.io
groupadd -f docker
usermod -aG docker jenkins
chmod 666 /var/run/docker.sock 2>/dev/null || true
echo "Permissions and packages updated"
"@

Write-Host "Starting Jenkins container..." -ForegroundColor Yellow
docker start jenkins

Write-Host "Waiting for Jenkins to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

Write-Host "Testing Docker access..." -ForegroundColor Yellow
$testResult = docker exec -u jenkins jenkins docker info 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Docker access working!" -ForegroundColor Green
    docker exec -u jenkins jenkins docker ps
} else {
    Write-Host "✗ Docker access still failing. Error:" -ForegroundColor Red
    Write-Host $testResult -ForegroundColor Red
    Write-Host "`nTrying alternative fix (running as root)..." -ForegroundColor Yellow
    Write-Host "You may need to recreate Jenkins container with --user root" -ForegroundColor Yellow
}

Write-Host "`nDone!" -ForegroundColor Green

