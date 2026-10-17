param (
    [string]$Target = "linux"
)

$ErrorActionPreference = "Stop"
$WorkspaceDir = (Get-Location).Path

switch ($Target.ToLower()) {
    "linux" {
        Write-Host "==> Building Linux binary via Podman..." -ForegroundColor Cyan
        podman build -t vpn-builder-linux -f Containerfile.build .
        podman run --cgroups=disabled --rm -v "${WorkspaceDir}:/workspace:Z" vpn-builder-linux
        Write-Host "==> Done! Artifact: dist/linux/vpn-launcher" -ForegroundColor Green
    }
    "windows" {
        Write-Host "==> Building Windows .exe via Podman (Wine)..." -ForegroundColor Cyan
        podman build -t vpn-builder-windows -f docker/Containerfile.windows .
        podman run --cgroups=disabled --rm -v "${WorkspaceDir}:/workspace:Z" vpn-builder-windows
        Write-Host "==> Done! Artifact: dist/windows/vpn-launcher.exe" -ForegroundColor Green
    }
    "clean" {
        Write-Host "==> Cleaning dist and build directories..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist, build, *.spec
    }
    default {
        Write-Host "Usage: .\build.ps1 -Target [linux|windows|clean]" -ForegroundColor Red
    }
}
