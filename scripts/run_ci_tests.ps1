<#
.SYNOPSIS
    officeForm Continuous Integration (CI) Test Suite Runner for Windows / PowerShell
.DESCRIPTION
    Runs Python compile check, JS check, Pytest with JUnit XML output, and Docker Compose syntax check.
.EXAMPLE
    .\scripts\run_ci_tests.ps1 -WithDockerBuild -WithDockerSmoke
#>

param(
    [switch]$WithDockerBuild,
    [switch]$WithDockerSmoke
)

$ErrorActionPreference = "Stop"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "        officeForm CI/CD Test Pipeline Execution     " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# Ensure JUnit output directory exists
if (-not (Test-Path "junit-reports")) {
    New-Item -ItemType Directory -Path "junit-reports" | Out-Null
}

# STAGE 1: Code Syntax & Compilation Checks
Write-Host "`n[Stage 1/4] Running Code Syntax & Compilation Checks..." -ForegroundColor Yellow
Write-Host -NoNewline "Checking Python syntax... "
python -B -c "
import pathlib
files = list(pathlib.Path('app').glob('*.py')) + [pathlib.Path('app_entry.py')] + list(pathlib.Path('scripts').glob('*.py')) + list(pathlib.Path('tests').glob('*.py'))
[compile(p.read_text(encoding='utf-8'), str(p), 'exec') for p in files]
print('OK')
"

if (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host -NoNewline "Checking JavaScript syntax... "
    node --check public/app.js
    Write-Host "OK" -ForegroundColor Green
} else {
    Write-Host "Node.js not installed on runner. Skipping JS syntax check." -ForegroundColor Yellow
}

# STAGE 2: Pytest Unit & API Integration Tests
Write-Host "`n[Stage 2/4] Executing Pytest Unit & Integration Suite..." -ForegroundColor Yellow
pytest tests `
    --junitxml=junit-reports/test-results.xml `
    --cov=app `
    --cov-report=term-missing `
    --cov-report=xml:coverage.xml `
    -v

if ($LASTEXITCODE -ne 0) {
    Write-Host "Pytest suite failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✓ All Pytest unit and integration tests passed!" -ForegroundColor Green

# STAGE 3: Docker Compose Syntax & Config Check
Write-Host "`n[Stage 3/4] Validating Docker Compose Configuration..." -ForegroundColor Yellow
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host -NoNewline "Validating docker-compose.yml syntax... "
    docker compose config --quiet
    Write-Host "OK" -ForegroundColor Green

    if ($WithDockerBuild) {
        Write-Host "`nBuilding Docker container image (officeform-web:latest)..." -ForegroundColor Yellow
        docker compose build web
        Write-Host "✓ Docker build successful!" -ForegroundColor Green
    }
} else {
    Write-Host "Docker CLI not found. Skipping Docker compose validation." -ForegroundColor Yellow
}

# STAGE 4: Optional Docker HTTP Smoke Test
if ($WithDockerSmoke -and (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "`n[Stage 4/4] Running Container HTTP Smoke Test..." -ForegroundColor Yellow
    $containerName = "officeform-ci-smoke-$PID"
    $testPort = 3999

    Write-Host "Starting ephemeral container $containerName on port $testPort..."
    docker run -d --name $containerName -p "${testPort}:3000" `
        -e DB_HOST=127.0.0.1 -e DB_NAME=test_db -e DB_USER=test -e DB_PASS=test `
        officeform-web:latest

    Start-Sleep -Seconds 4

    Write-Host -NoNewline "Testing HTTP endpoint readiness... "
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:${testPort}/" -UseBasicParsing -TimeoutSec 5
        $status = $response.StatusCode
    } catch {
        $status = $_.Exception.Response.StatusCode.value__
    }

    Write-Host "Tearing down smoke test container..."
    docker rm -f $containerName | Out-Null

    if ($status -ge 200 -and $status -lt 500) {
        Write-Host "✓ Container smoke test passed (HTTP Status: $status)!" -ForegroundColor Green
    } else {
        Write-Host "✗ Container smoke test failed (HTTP Status: $status)" -ForegroundColor Red
        exit 1
    }
}

Write-Host "`n=====================================================" -ForegroundColor Green
Write-Host "    ✓ CI/CD Test Pipeline Execution Complete!        " -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
