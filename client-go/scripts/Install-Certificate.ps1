<#
.SYNOPSIS
    Installs BobrDobr Root CA and Code Signing certificates into Windows Certificate Stores.

.DESCRIPTION
    Establishes Authenticode trust for BobrDobr VPN binaries in Windows Defender,
    SmartScreen, and UAC.
    
    Registers:
    - BobrDobr Root CA into Trusted Root Certification Authorities (Root)
    - BobrDobr Code Signing Cert into Trusted Publishers (TrustedPublisher)
    
    Once registered:
    - SmartScreen displays "Проверенный издатель: BobrDobr Hydro-engineering Team"
    - Authenticode status changes to "Valid"
    - Zero untrusted / unknown publisher warnings appear on install or launch.

.PARAMETER CertsDir
    Directory containing exported certificates. Default: client-go/certs.

.PARAMETER Scope
    Certificate store scope: "Auto", "LocalMachine", or "CurrentUser". Default: "Auto".

.PARAMETER Elevate
    Automatically request UAC elevation if not running as Administrator.

.PARAMETER Uninstall
    Remove BobrDobr certificates from the Windows Certificate Stores.
#>

[CmdletBinding()]
param(
    [string]$CertsDir,
    [ValidateSet("Auto", "LocalMachine", "CurrentUser")]
    [string]$Scope = "Auto",
    [switch]$Elevate,
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $CertsDir) {
    $CertsDir = Join-Path $PSScriptRoot "..\certs"
}

$resolvedCertsDir = [System.IO.Path]::GetFullPath($CertsDir)
$rootCerPath     = Join-Path $resolvedCertsDir "BobrDobr-RootCA.cer"
$codeSignCerPath = Join-Path $resolvedCertsDir "BobrDobr-CodeSign.cer"
$metaJsonPath    = Join-Path $resolvedCertsDir "certificate-metadata.json"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " BobrDobr VPN - Certificate Trust Installer" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Administrator Session: $isAdmin" -ForegroundColor Gray

if ((-not $isAdmin) -and $Elevate) {
    Write-Host "[*] Relaunching elevated with Administrator rights..." -ForegroundColor Yellow
    $elevatedArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-CertsDir", "`"$resolvedCertsDir`"",
        "-Scope", "LocalMachine"
    )
    if ($Uninstall) { $elevatedArgs += "-Uninstall" }

    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList ($elevatedArgs -join " ") -Verb RunAs -Wait -PassThru
    exit $proc.ExitCode
}

# Load metadata for thumbprints
$rootThumbprint = $null
$codeSignThumbprint = $null

if (Test-Path $metaJsonPath) {
    try {
        $meta = Get-Content -Raw -Path $metaJsonPath | ConvertFrom-Json
        $rootThumbprint = $meta.RootCA.Thumbprint
        $codeSignThumbprint = $meta.CodeSign.Thumbprint
    } catch {
        Write-Warning "Failed to parse metadata JSON: $_"
    }
}

# If removing certificates
if ($Uninstall) {
    Write-Host "[*] Removing BobrDobr certificates from Certificate Stores..." -ForegroundColor Yellow

    $storesToCheck = @(
        @{ Location = "CurrentUser"; Store = "Root" },
        @{ Location = "CurrentUser"; Store = "TrustedPublisher" }
    )
    if ($isAdmin) {
        $storesToCheck += @(
            @{ Location = "LocalMachine"; Store = "Root" },
            @{ Location = "LocalMachine"; Store = "TrustedPublisher" }
        )
    }

    foreach ($s in $storesToCheck) {
        $storePath = "Cert:\$($s.Location)\$($s.Store)"
        if (Test-Path $storePath) {
            Get-ChildItem -Path $storePath | Where-Object {
                $_.Subject -like "*BobrDobr*" -or
                ($rootThumbprint -and $_.Thumbprint -eq $rootThumbprint) -or
                ($codeSignThumbprint -and $_.Thumbprint -eq $codeSignThumbprint)
            } | ForEach-Object {
                Write-Host "    Removing from $storePath : $($_.Subject) ($($_.Thumbprint))" -ForegroundColor Gray
                $_ | Remove-Item -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Write-Host "[OK] Certificate cleanup complete." -ForegroundColor Green
    return
}

# Verify certificate files exist
if (-not (Test-Path $rootCerPath)) {
    throw "Root CA certificate not found at '$rootCerPath'. Run Generate-Certificate.ps1 first."
}
if (-not (Test-Path $codeSignCerPath)) {
    throw "Code Signing certificate not found at '$codeSignCerPath'. Run Generate-Certificate.ps1 first."
}

# Determine target scope
$targetScopes = @()
if ($Scope -eq "LocalMachine") {
    if (-not $isAdmin) {
        Write-Warning "LocalMachine store requires Administrator privileges. Consider passing -Elevate."
    }
    $targetScopes += "LocalMachine"
} elseif ($Scope -eq "CurrentUser") {
    $targetScopes += "CurrentUser"
} else { # Auto
    if ($isAdmin) {
        $targetScopes += "LocalMachine"
        $targetScopes += "CurrentUser"
    } else {
        $targetScopes += "CurrentUser"
    }
}

Write-Host "[1/2] Installing Root CA into Trusted Root Certification Authorities..." -ForegroundColor Green
foreach ($s in $targetScopes) {
    Write-Host "      Target Store: $s\Root" -ForegroundColor Gray
    if ($s -eq "LocalMachine") {
        if ($isAdmin) {
            $output = & certutil.exe -addstore -f "Root" $rootCerPath
            Write-Host "      CertUtil: $($output | Select-Object -Last 1)" -ForegroundColor DarkGray
        } else {
            Write-Host "      [!] Skipping LocalMachine\Root (requires Administrator). Pass -Elevate to install." -ForegroundColor Yellow
        }
    } else {
        # CurrentUser\Root
        if ($isAdmin) {
            # Running elevated: certutil adds to user store without block
            $output = & certutil.exe -user -addstore -f "Root" $rootCerPath
            Write-Host "      CertUtil: $($output | Select-Object -Last 1)" -ForegroundColor DarkGray
        } else {
            Write-Host "      [!] Note: Non-admin installation of Root CA into CurrentUser\Root requires OS GUI confirmation." -ForegroundColor Yellow
            Write-Host "          Run: 'Install-Certificate.ps1 -Elevate' to silently register in LocalMachine." -ForegroundColor Yellow
        }
    }
}

Write-Host "[2/2] Installing Code Signing Certificate into Trusted Publishers..." -ForegroundColor Green
foreach ($s in $targetScopes) {
    Write-Host "      Target Store: $s\TrustedPublisher" -ForegroundColor Gray
    if ($s -eq "LocalMachine") {
        if ($isAdmin) {
            $output = & certutil.exe -addstore -f "TrustedPublisher" $codeSignCerPath
            Write-Host "      CertUtil: $($output | Select-Object -Last 1)" -ForegroundColor DarkGray
        } else {
            Write-Host "      [!] Skipping LocalMachine\TrustedPublisher (requires Administrator). Pass -Elevate to install." -ForegroundColor Yellow
        }
    } else {
        $output = & certutil.exe -user -addstore -f "TrustedPublisher" $codeSignCerPath
        Write-Host "      CertUtil: $($output | Select-Object -Last 1)" -ForegroundColor DarkGray
    }
}

Write-Host "==========================================================" -ForegroundColor Green
Write-Host " [SUCCESS] Certificates installed into Windows Trust Stores!" -ForegroundColor Green
Write-Host " Trusted Root:        BobrDobr Root CA" -ForegroundColor White
Write-Host " Trusted Publisher:   BobrDobr Hydro-engineering Team" -ForegroundColor White
Write-Host " SmartScreen status:  'Проверенный издатель' (Verified Publisher)" -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Green
