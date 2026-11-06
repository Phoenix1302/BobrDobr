<#
.SYNOPSIS
    Signs Windows executables and installers using Authenticode with RFC 3161 timestamping.

.DESCRIPTION
    Signs .exe, .dll, .sys, and .ps1 files with the BobrDobr Code Signing Certificate.
    Automatically leverages signtool.exe if available, or native PowerShell Set-AuthenticodeSignature.
    Applies RFC 3161 timestamps via DigiCert or Sectigo to ensure signatures remain valid
    long after certificate expiration.

.PARAMETER FilePath
    Path(s) to executable or installer files to sign. Accepts pipeline input and wildcards.

.PARAMETER CertPath
    Path to the Code Signing PFX certificate. Default: client-go/certs/BobrDobr-CodeSign.pfx.

.PARAMETER Password
    Password for the PFX file. Default: BobrDobr2026!SecureKey.

.PARAMETER TimestampServer
    Primary RFC 3161 Timestamp URL. Default: http://timestamp.digicert.com.

.PARAMETER HashAlgorithm
    Digest hash algorithm. Default: SHA256.

.PARAMETER Description
    Signature description. Default: "BobrDobr VPN".

.PARAMETER Force
    Re-sign files even if already signed with a valid signature.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0, ValueFromPipeline = $true, ValueFromPipelineByPropertyName = $true)]
    [string[]]$FilePath,

    [string]$CertPath,
    [string]$Password = "BobrDobr2026!SecureKey",
    [string]$TimestampServer = "http://timestamp.digicert.com",
    [string]$HashAlgorithm = "SHA256",
    [string]$Description = "BobrDobr VPN",
    [string]$DescriptionUrl = "https://github.com/Phoenix1302/BobrDobr",
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $CertPath) {
    $CertPath = Join-Path $PSScriptRoot "..\certs\BobrDobr-CodeSign.pfx"
}

$resolvedCertPath = [System.IO.Path]::GetFullPath($CertPath)
if (-not (Test-Path $resolvedCertPath)) {
    throw "Code signing certificate not found at '$resolvedCertPath'. Please run Generate-Certificate.ps1 first."
}

# Timestamp server fallback pool
$timestampPool = @(
    $TimestampServer,
    "http://timestamp.sectigo.com",
    "http://timestamp.entrust.net/TSS/RFC3161sha2TS",
    "http://rb.symcb.com/rpa"
) | Select-Object -Unique

# Check for signtool.exe in PATH or Windows Kits
$signtoolCmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
if (-not $signtoolCmd) {
    $sdkLocations = @(
        "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe",
        "C:\Program Files\Windows Kits\10\bin\*\x64\signtool.exe"
    )
    $found = Get-ChildItem -Path $sdkLocations -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $signtoolCmd = $found.FullName
    }
}

# Load certificate into memory for Set-AuthenticodeSignature
$storageFlags = [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable -bor `
                [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::PersistKeySet
$x509Cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(
    $resolvedCertPath,
    $Password,
    $storageFlags
)

# Normalize FilePath array (handles comma-separated strings passed via CLI)
$expandedPaths = @()
foreach ($p in $FilePath) {
    if ($p -match ",") {
        $expandedPaths += ($p -split "," | ForEach-Object { $_.Trim() })
    } else {
        $expandedPaths += $p.Trim()
    }
}
$FilePath = $expandedPaths
$results = @()

foreach ($pathPattern in $FilePath) {
    $matchedFiles = Get-ChildItem -Path $pathPattern -File -ErrorAction SilentlyContinue
    if (-not $matchedFiles) {
        Write-Warning "No files matched pattern: $pathPattern"
        continue
    }

    foreach ($file in $matchedFiles) {
        $target = $file.FullName
        Write-Host "`n[*] Processing: $target" -ForegroundColor Cyan

        # Check existing signature
        $existingSig = Get-AuthenticodeSignature -FilePath $target
        if ($existingSig.Status -eq "Valid" -and (-not $Force)) {
            Write-Host "    [SKIP] File already has a valid signature: $($existingSig.SignerCertificate.Subject)" -ForegroundColor Yellow
            $results += [PSCustomObject]@{
                File      = $target
                Status    = "AlreadySigned"
                Signer    = $existingSig.SignerCertificate.Subject
                Timestamp = $existingSig.TimeStamperCertificate.Subject
            }
            continue
        }

        $signedSuccessfully = $false
        $lastError = $null

        # Attempt signing with timestamp fallbacks
        foreach ($tsUrl in $timestampPool) {
            try {
                if ($signtoolCmd) {
                    Write-Host "    Signing via signtool.exe with timestamp: $tsUrl" -ForegroundColor Gray
                    $signArgs = @(
                        "sign",
                        "/f", "`"$resolvedCertPath`"",
                        "/p", "`"$Password`"",
                        "/fd", $HashAlgorithm,
                        "/tr", $tsUrl,
                        "/td", $HashAlgorithm,
                        "/d", "`"$Description`"",
                        "/du", "`"$DescriptionUrl`"",
                        "`"$target`""
                    )
                    $proc = Start-Process -FilePath $signtoolCmd -ArgumentList ($signArgs -join " ") -Wait -PassThru -NoNewWindow
                    if ($proc.ExitCode -eq 0) {
                        $signedSuccessfully = $true
                        break
                    }
                } else {
                    Write-Host "    Signing via Set-AuthenticodeSignature with timestamp: $tsUrl" -ForegroundColor Gray
                    $sigResult = Set-AuthenticodeSignature `
                        -FilePath $target `
                        -Certificate $x509Cert `
                        -TimestampServer $tsUrl `
                        -HashAlgorithm $HashAlgorithm `
                        -ErrorAction Stop

                    if ($sigResult -and $sigResult.SignerCertificate) {
                        $signedSuccessfully = $true
                        break
                    }
                }
            } catch {
                $lastError = $_.Exception.Message
                Write-Host "    [!] Timestamp attempt failed ($tsUrl): $lastError. Trying next..." -ForegroundColor Yellow
            }
        }

        # If timestamping failed on all servers, attempt fallback sign without timestamp
        if (-not $signedSuccessfully) {
            Write-Warning "Timestamp servers unreachable. Attempting offline signature without RFC 3161 timestamp..."
            try {
                $sigResult = Set-AuthenticodeSignature `
                    -FilePath $target `
                    -Certificate $x509Cert `
                    -HashAlgorithm $HashAlgorithm `
                    -ErrorAction Stop
                if ($sigResult -and $sigResult.SignerCertificate) {
                    $signedSuccessfully = $true
                }
            } catch {
                $lastError = $_.Exception.Message
            }
        }

        if (-not $signedSuccessfully) {
            Write-Error "Failed to sign '$target': $lastError"
            $results += [PSCustomObject]@{
                File      = $target
                Status    = "Failed"
                Error     = $lastError
                Signer    = $null
                Timestamp = $null
            }
            continue
        }

        # Verify signature
        $verify = Get-AuthenticodeSignature -FilePath $target
        $signerSubject = if ($verify.SignerCertificate) { $verify.SignerCertificate.Subject } else { "None" }
        $tsSubject = if ($verify.TimeStamperCertificate) { $verify.TimeStamperCertificate.Subject } else { "None" }

        if ($verify.Status -eq "Valid") {
            Write-Host "    [OK] Signature verified: VALID" -ForegroundColor Green
            Write-Host "         Signer:    $signerSubject" -ForegroundColor Green
            Write-Host "         Timestamp: $tsSubject" -ForegroundColor Green
        } else {
            # UnknownError is expected if Root CA is not yet imported into LocalMachine/CurrentUser Root store
            Write-Host "    [OK] Signature block embedded successfully!" -ForegroundColor Green
            Write-Host "         Signer:    $signerSubject" -ForegroundColor Gray
            Write-Host "         Timestamp: $tsSubject" -ForegroundColor Gray
            Write-Host "         Status:    $($verify.Status) ($($verify.StatusMessage))" -ForegroundColor Yellow
            Write-Host "         [NOTE] Run 'Install-Certificate.ps1' to trust this publisher in Windows Defender / SmartScreen." -ForegroundColor Yellow
        }

        $results += [PSCustomObject]@{
            File      = $target
            Status    = $verify.Status.ToString()
            Signer    = $signerSubject
            Timestamp = $tsSubject
        }
    }
}

return $results
