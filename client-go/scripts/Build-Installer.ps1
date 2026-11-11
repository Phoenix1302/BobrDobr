<#
.SYNOPSIS
    Builds and signs the BobrDobr VPN Inno Setup installer.

.DESCRIPTION
    1. Locates Inno Setup 6 (ISCC.exe).
    2. Validates dependencies (BobrDobr.exe, bin/windows/*, assets).
    3. Generates certificates if missing.
    4. Compiles client-go/build/windows/installer/BobrDobr-Setup.iss into BobrDobr-Setup.exe.
    5. Signs the compiled installer using Authenticode + RFC 3161 Timestamping.
    6. Verifies the digital signature and outputs SHA256 checksums.

.PARAMETER Version
    Installer version string. Default: 1.3.0.

.PARAMETER OutputDir
    Directory for the compiled installer. Default: dist/installer.

.PARAMETER NoSign
    Skip code signing of the compiled installer.

.PARAMETER Clean
    Clean the output directory before compiling.
#>

[CmdletBinding()]
param(
    [string]$Version = "1.3.1",
    [string]$OutputDir,
    [switch]$NoSign,
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$issPath  = Join-Path $repoRoot "client-go\build\windows\installer\BobrDobr-Setup.iss"

if (-not $OutputDir) {
    $OutputDir = Join-Path $repoRoot "dist\installer"
}
$resolvedOutputDir = [System.IO.Path]::GetFullPath($OutputDir)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " BobrDobr VPN - Windows Installer Builder & Signer" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Repository Root: $repoRoot" -ForegroundColor Gray
Write-Host " ISS Script:      $issPath" -ForegroundColor Gray
Write-Host " Version:         $Version" -ForegroundColor Gray
Write-Host " Output Dir:      $resolvedOutputDir" -ForegroundColor Gray

# 1. Locate ISCC.exe
$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$isccPath = $null

foreach ($cand in $isccCandidates) {
    if (Test-Path $cand) {
        $isccPath = $cand
        break
    }
}

if (-not $isccPath) {
    $cmd = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        $isccPath = $cmd.Source
    }
}

if (-not $isccPath) {
    throw "Inno Setup 6 compiler (ISCC.exe) not found. Please install Inno Setup 6 from https://jrsoftware.org/isdl.php"
}

Write-Host "[*] Inno Setup Compiler found: $isccPath" -ForegroundColor Green

# 2. Prepare Output Directory
if ($Clean -and (Test-Path $resolvedOutputDir)) {
    Write-Host "[*] Cleaning output directory: $resolvedOutputDir" -ForegroundColor Yellow
    Remove-Item -Path $resolvedOutputDir -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path $resolvedOutputDir)) {
    New-Item -ItemType Directory -Path $resolvedOutputDir -Force | Out-Null
}

# 3. Ensure BobrDobr.exe binary is available
$distExe = Join-Path $repoRoot "dist\windows\BobrDobr.exe"
if (-not (Test-Path $distExe)) {
    $altExe = Join-Path $repoRoot "dist\windows\BobrDobr-VPN-v1.1.1.exe"
    if (Test-Path $altExe) {
        Write-Host "[*] Linking $altExe -> $distExe" -ForegroundColor Yellow
        New-Item -ItemType HardLink -Path $distExe -Target $altExe -Force | Out-Null
    }
}

# Ensure dist/windows/bin directory exists and contains openconnect-worker.exe
$distWindowsBinDir = Join-Path $repoRoot "dist\windows\bin"
if (-not (Test-Path $distWindowsBinDir)) {
    New-Item -ItemType Directory -Path $distWindowsBinDir -Force | Out-Null
}
$workerSrc = Join-Path $repoRoot "bin\windows\openconnect-worker.exe"
if (Test-Path $workerSrc) {
    Copy-Item -Path $workerSrc -Destination (Join-Path $distWindowsBinDir "openconnect-worker.exe") -Force
    Copy-Item -Path $workerSrc -Destination (Join-Path $repoRoot "dist\windows\openconnect-worker.exe") -Force
}

# 4. Check or Generate Code Signing Certificates
$certPfx = Join-Path $repoRoot "client-go\certs\BobrDobr-CodeSign.pfx"
if ((-not $NoSign) -and (-not (Test-Path $certPfx))) {
    Write-Host "[*] Code signing certificate not found. Generating now..." -ForegroundColor Yellow
    $genScript = Join-Path $PSScriptRoot "Generate-Certificate.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $genScript
    if (-not (Test-Path $certPfx)) {
        throw "Failed to generate code signing certificate at '$certPfx'."
    }
}

# 5. Pre-sign payload binaries before packaging
if (-not $NoSign) {
    Write-Host "[*] Pre-signing application and backend binaries..." -ForegroundColor Green
    $signScript = Join-Path $PSScriptRoot "Sign-Binary.ps1"
    
    $binariesToSign = @()
    if (Test-Path $distExe) { $binariesToSign += $distExe }
    
    $backendBinDir = Join-Path $repoRoot "bin\windows"
    if (Test-Path $backendBinDir) {
        $binFiles = Get-ChildItem -Path $backendBinDir -File | Where-Object { $_.Extension -in '.exe', '.dll' } | Select-Object -ExpandProperty FullName
        $binariesToSign += $binFiles
    }

    if (Test-Path $distWindowsBinDir) {
        $distBinFiles = Get-ChildItem -Path $distWindowsBinDir -File | Where-Object { $_.Extension -in '.exe', '.dll' } | Select-Object -ExpandProperty FullName
        $binariesToSign += $distBinFiles
    }

    $distWorker = Join-Path $repoRoot "dist\windows\openconnect-worker.exe"
    if (Test-Path $distWorker) {
        $binariesToSign += $distWorker
    }

    $binariesToSign = $binariesToSign | Select-Object -Unique

    if ($binariesToSign.Count -gt 0) {
        Write-Host "    Binaries queued for code signing:" -ForegroundColor Gray
        foreach ($b in $binariesToSign) {
            Write-Host "      - $b" -ForegroundColor Gray
        }
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $signScript -FilePath ($binariesToSign -join ",")
    }
}

# 5. Compile Inno Setup Script
Write-Host "[*] Compiling Inno Setup Script..." -ForegroundColor Green
$isccArgs = @(
    "/Qp",
    "/DAppVersion=$Version",
    "/DSourceDir=$repoRoot",
    "/DOutputDir=$resolvedOutputDir",
    "`"$issPath`""
)

$proc = Start-Process -FilePath $isccPath -ArgumentList ($isccArgs -join " ") -Wait -PassThru -NoNewWindow
if ($proc.ExitCode -ne 0) {
    throw "Inno Setup compilation failed with exit code $($proc.ExitCode)."
}

$versionedSetupExe = Join-Path $resolvedOutputDir "BobrDobr-Setup-v$Version.exe"
if (-not (Test-Path $versionedSetupExe)) {
    throw "Expected setup binary not found at '$versionedSetupExe'."
}

Write-Host "[OK] Inno Setup compilation succeeded: $versionedSetupExe" -ForegroundColor Green

# 6. Sign the Setup Installer
if (-not $NoSign) {
    Write-Host "[*] Signing installer binary with Authenticode + RFC 3161 Timestamp..." -ForegroundColor Green
    $signScript = Join-Path $PSScriptRoot "Sign-Binary.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $signScript -FilePath $versionedSetupExe -Force
}

# Create copy BobrDobr-Setup.exe in dist/installer
$genericSetupExe = Join-Path $resolvedOutputDir "BobrDobr-Setup.exe"
Copy-Item -Path $versionedSetupExe -Destination $genericSetupExe -Force
Write-Host "[OK] Created generic installer copy: $genericSetupExe" -ForegroundColor Green

# 7. Verification & Checksum
$sig = Get-AuthenticodeSignature -FilePath $versionedSetupExe
$hash = (Get-FileHash -Path $versionedSetupExe -Algorithm SHA256).Hash
$fileInfo = Get-Item -Path $versionedSetupExe

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " BUILD AND SIGNING REPORT" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host " Setup File:        $versionedSetupExe" -ForegroundColor White
Write-Host " Generic Copy:      $genericSetupExe" -ForegroundColor White
Write-Host " Size:              $([math]::Round($fileInfo.Length / 1MB, 2)) MB ($($fileInfo.Length) bytes)" -ForegroundColor White
Write-Host " SHA-256:           $hash" -ForegroundColor White
Write-Host " Signer:            $($sig.SignerCertificate.Subject)" -ForegroundColor White
Write-Host " Timestamp Server:  $($sig.TimeStamperCertificate.Subject)" -ForegroundColor White
Write-Host " Signature Status:  $($sig.Status)" -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Green

return [PSCustomObject]@{
    SetupPath   = $versionedSetupExe
    GenericPath = $genericSetupExe
    SizeBytes   = $fileInfo.Length
    SHA256      = $hash
    Signer      = $sig.SignerCertificate.Subject
    Timestamp   = $sig.TimeStamperCertificate.Subject
    Status      = $sig.Status.ToString()
}
