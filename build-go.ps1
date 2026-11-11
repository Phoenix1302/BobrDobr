<#
.SYNOPSIS
    Master build script for BobrDobr VPN (Go + WebView2).
#>

[CmdletBinding()]
param(
    [string]$Version = "1.3.0",
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$clientGoDir = Join-Path $repoRoot "client-go"
$binDir = Join-Path $clientGoDir "bin"
$distWindowsDir = Join-Path $repoRoot "dist\windows"
$distInstallerDir = Join-Path $repoRoot "dist\installer"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " BobrDobr VPN - Complete Build Pipeline (Go Native Engine)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Version:     $Version" -ForegroundColor Gray
Write-Host " Repository:  $repoRoot" -ForegroundColor Gray

# 1. Tests
if (-not $SkipTests) {
    Write-Host "`n[*] Running Go unit tests in container..." -ForegroundColor Yellow
    podman run --rm -v "${clientGoDir}:/workspace:Z" -w /workspace docker.io/library/golang:1.24-alpine go test -mod=vendor ./...
    if ($LASTEXITCODE -ne 0) {
        throw "Unit tests failed!"
    }
    Write-Host "[OK] All tests passed!" -ForegroundColor Green
}

# 2. Compile Windows Binary
Write-Host "`n[*] Compiling BobrDobr.exe (Subsystem 2 GUI with embedded icons)..." -ForegroundColor Yellow
$distWindowsBinDir = Join-Path $distWindowsDir "bin"
New-Item -ItemType Directory -Force -Path $binDir, $distWindowsDir, $distWindowsBinDir | Out-Null

$sysoPath = Join-Path $clientGoDir "cmd\bobrdobr\rsrc_windows_amd64.syso"
Write-Host "[*] Generating Windows PE icon, manifest, and version resources..." -ForegroundColor Yellow
podman run --rm -v "${repoRoot}:/workspace:Z" -w /workspace docker.io/library/golang:1.24-alpine sh -c "go install github.com/josephspurrier/goversioninfo/cmd/goversioninfo@latest && goversioninfo -o /workspace/client-go/cmd/bobrdobr/rsrc_windows_amd64.syso /workspace/client-go/build/windows/versioninfo.json"
if ($LASTEXITCODE -ne 0) {
    throw "goversioninfo resource generation failed!"
}

# Build without -s -w stripping: keeping Go symbol tables and runtime metadata prevents false-positive ML detections (Bearfoos.A!ml)
podman run --rm -v "${clientGoDir}:/workspace:Z" -w /workspace -e CGO_ENABLED=0 -e GOOS=windows -e GOARCH=amd64 docker.io/library/golang:1.24-alpine go build -mod=vendor -ldflags="-H windowsgui" -o /workspace/bin/BobrDobr.exe ./cmd/bobrdobr
if ($LASTEXITCODE -ne 0) {
    throw "BobrDobr.exe compilation failed!"
}

Copy-Item (Join-Path $binDir "BobrDobr.exe") (Join-Path $distWindowsDir "BobrDobr.exe") -Force
$exeSize = (Get-Item (Join-Path $binDir "BobrDobr.exe")).Length / 1MB
Write-Host ("[OK] Binary compiled: {0:N2} MB" -f $exeSize) -ForegroundColor Green

# Ensure openconnect-worker.exe is present in bin/windows and copied to dist/windows/bin/
$workerSrc = Join-Path $repoRoot "bin\windows\openconnect-worker.exe"
if (-not (Test-Path $workerSrc)) {
    Write-Host "[*] Compiling openconnect-worker.exe..." -ForegroundColor Yellow
    powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "build-openconnect-worker.ps1")
}

if (Test-Path $workerSrc) {
    Copy-Item $workerSrc (Join-Path $distWindowsDir "openconnect-worker.exe") -Force
    Copy-Item $workerSrc (Join-Path $distWindowsBinDir "openconnect-worker.exe") -Force
    Write-Host "[OK] openconnect-worker.exe staged to dist/windows/ and dist/windows/bin/" -ForegroundColor Green
}

# 3. Build Trusted Installer
Write-Host "`n[*] Building and signing Inno Setup installer..." -ForegroundColor Yellow
powershell -ExecutionPolicy Bypass -File (Join-Path $clientGoDir "scripts\Build-Installer.ps1") -Version $Version -OutputDir $distInstallerDir
if ($LASTEXITCODE -ne 0) {
    throw "Installer build failed!"
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " [SUCCESS] Build and packaging complete!" -ForegroundColor Green
Write-Host " Installer: $distInstallerDir\BobrDobr-Setup-v$Version.exe" -ForegroundColor Cyan
Write-Host " Generic:   $distInstallerDir\BobrDobr-Setup.exe" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Green
