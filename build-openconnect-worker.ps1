<#
.SYNOPSIS
    Builds the OpenConnect Pure-Go CSTP Worker (openconnect-worker.exe) for Windows x64.
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$workerDir = Join-Path $repoRoot "openconnect-worker"
$binWindows = Join-Path $repoRoot "bin\windows"
$distWindows = Join-Path $repoRoot "dist\windows"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " OpenConnect Pure-Go CSTP Worker - Build Pipeline" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

Write-Host "`n[*] Compiling openconnect-worker.exe in container..." -ForegroundColor Yellow
podman run --rm -v "${repoRoot}:/workspace:Z" -w /workspace/openconnect-worker -e CGO_ENABLED=0 -e GOOS=windows -e GOARCH=amd64 docker.io/library/golang:1.24-alpine go build -ldflags="-s -w" -o /workspace/bin/windows/openconnect-worker.exe main.go
if ($LASTEXITCODE -ne 0) {
    throw "openconnect-worker.exe compilation failed!"
}

Copy-Item (Join-Path $binWindows "openconnect-worker.exe") (Join-Path $distWindows "openconnect-worker.exe") -Force

$sizeMB = (Get-Item (Join-Path $binWindows "openconnect-worker.exe")).Length / 1MB
Write-Host ("[OK] openconnect-worker.exe compiled: {0:N2} MB" -f $sizeMB) -ForegroundColor Green
Write-Host " Output: $binWindows\openconnect-worker.exe" -ForegroundColor Cyan
Write-Host " Dist:   $distWindows\openconnect-worker.exe" -ForegroundColor Cyan
