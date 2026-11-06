<#
.SYNOPSIS
    Generates a dedicated Root CA and Code Signing Certificate for BobrDobr VPN.

.DESCRIPTION
    Creates an Authenticode-compliant PKI hierarchy:
    1. BobrDobr Root CA (Self-Signed Root Certificate Authority, 4096-bit RSA, SHA-256).
    2. BobrDobr Code Signing Certificate (issued by Root CA, 2048-bit RSA, SHA-256, CodeSigning EKU).
    Exports .pfx bundles (with password), .cer public certificates, and metadata JSON.

.PARAMETER OutputDir
    Directory where certificates will be saved. Default: client-go/certs.

.PARAMETER Subject
    Subject DN for Code Signing Certificate. Default: CN=BobrDobr Hydro-engineering Team, O=BobrDobr Hydro-engineering Team, C=RU.

.PARAMETER RootSubject
    Subject DN for Root CA. Default: CN=BobrDobr Root CA, O=BobrDobr Hydro-engineering Team, C=RU.

.PARAMETER Password
    Password for exported PFX files. Default: BobrDobr2026!SecureKey.

.PARAMETER ValidYears
    Validity period in years for Code Signing cert. Default: 5.

.PARAMETER RootValidYears
    Validity period in years for Root CA cert. Default: 10.

.PARAMETER Force
    Overwrite existing certificate files if they exist.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$OutputDir,

    [string]$Subject = "CN=BobrDobr Hydro-engineering Team, O=BobrDobr Hydro-engineering Team, C=RU",
    [string]$RootSubject = "CN=BobrDobr Root CA, O=BobrDobr Hydro-engineering Team, C=RU",
    [string]$Password = "BobrDobr2026!SecureKey",
    [int]$ValidYears = 5,
    [int]$RootValidYears = 10,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $OutputDir) {
    $OutputDir = Join-Path $PSScriptRoot "..\certs"
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " BobrDobr VPN - Certificate Authority & Code Sign Generator" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Resolve output path
$resolvedOutputDir = [System.IO.Path]::GetFullPath($OutputDir)
if (-not (Test-Path $resolvedOutputDir)) {
    Write-Host "[*] Creating certificates directory: $resolvedOutputDir" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $resolvedOutputDir -Force | Out-Null
}

$rootCerPath     = Join-Path $resolvedOutputDir "BobrDobr-RootCA.cer"
$rootCrtPath     = Join-Path $resolvedOutputDir "BobrDobr-RootCA.crt"
$rootPfxPath     = Join-Path $resolvedOutputDir "BobrDobr-RootCA.pfx"
$codeSignCerPath = Join-Path $resolvedOutputDir "BobrDobr-CodeSign.cer"
$codeSignCrtPath = Join-Path $resolvedOutputDir "BobrDobr-CodeSign.crt"
$codeSignPfxPath = Join-Path $resolvedOutputDir "BobrDobr-CodeSign.pfx"
$metaJsonPath    = Join-Path $resolvedOutputDir "certificate-metadata.json"

if ((Test-Path $codeSignPfxPath) -and (-not $Force)) {
    Write-Host "[!] Existing certificates found at $codeSignPfxPath" -ForegroundColor Yellow
    Write-Host "    Use -Force to regenerate." -ForegroundColor Yellow
    return [PSCustomObject]@{
        Status             = "Existing"
        RootCer            = $rootCerPath
        CodeSignCer        = $codeSignCerPath
        CodeSignPfx        = $codeSignPfxPath
        Metadata           = $metaJsonPath
    }
}

$secPassword = ConvertTo-SecureString -String $Password -Force -AsPlainText

Write-Host "[1/4] Generating Root Certificate Authority (CA)..." -ForegroundColor Green
$rootCert = New-SelfSignedCertificate `
    -Subject $RootSubject `
    -KeyAlgorithm RSA `
    -KeyLength 4096 `
    -HashAlgorithm SHA256 `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -KeyUsage CertSign, CRLSign, DigitalSignature `
    -KeyUsageProperty All `
    -Type Custom `
    -TextExtension @("2.5.29.19={critical}{text}ca=1") `
    -NotAfter (Get-Date).AddYears($RootValidYears) `
    -FriendlyName "BobrDobr Root CA"

Write-Host "      Root CA Thumbprint: $($rootCert.Thumbprint)" -ForegroundColor Gray

Write-Host "[2/4] Generating Code Signing Certificate signed by Root CA..." -ForegroundColor Green
$codeSignCert = New-SelfSignedCertificate `
    -Subject $Subject `
    -Signer $rootCert `
    -KeyAlgorithm RSA `
    -KeyLength 2048 `
    -HashAlgorithm SHA256 `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -Type CodeSigningCert `
    -KeyUsage DigitalSignature `
    -NotAfter (Get-Date).AddYears($ValidYears) `
    -FriendlyName "BobrDobr VPN Authenticode Code Signing"

Write-Host "      CodeSign Thumbprint: $($codeSignCert.Thumbprint)" -ForegroundColor Gray

Write-Host "[3/4] Exporting certificates..." -ForegroundColor Green

# Export Root CA public cert (DER and PEM)
Export-Certificate -Cert $rootCert -FilePath $rootCerPath -Type CERT | Out-Null
$rootBase64 = [Convert]::ToBase64String($rootCert.RawData, [Base64FormattingOptions]::InsertLineBreaks)
$rootPem = "-----BEGIN CERTIFICATE-----`r`n$rootBase64`r`n-----END CERTIFICATE-----`r`n"
[System.IO.File]::WriteAllText($rootCrtPath, $rootPem, [System.Text.Encoding]::ASCII)

# Export Root CA PFX (with private key)
Export-PfxCertificate -Cert $rootCert -FilePath $rootPfxPath -Password $secPassword | Out-Null

# Export Code Signing public cert (DER and PEM)
Export-Certificate -Cert $codeSignCert -FilePath $codeSignCerPath -Type CERT | Out-Null
$codeBase64 = [Convert]::ToBase64String($codeSignCert.RawData, [Base64FormattingOptions]::InsertLineBreaks)
$codePem = "-----BEGIN CERTIFICATE-----`r`n$codeBase64`r`n-----END CERTIFICATE-----`r`n"
[System.IO.File]::WriteAllText($codeSignCrtPath, $codePem, [System.Text.Encoding]::ASCII)

# Export Code Signing PFX (contains private key and chain)
Export-PfxCertificate -Cert $codeSignCert -FilePath $codeSignPfxPath -Password $secPassword -ChainOption BuildChain | Out-Null

Write-Host "[4/4] Writing metadata JSON..." -ForegroundColor Green
$metadata = [PSCustomObject]@{
    GeneratedAt          = (Get-Date).ToString("o")
    RootCA = [PSCustomObject]@{
        Subject          = $rootCert.Subject
        Issuer           = $rootCert.Issuer
        Thumbprint       = $rootCert.Thumbprint
        SerialNumber     = $rootCert.SerialNumber
        NotBefore        = $rootCert.NotBefore.ToString("o")
        NotAfter         = $rootCert.NotAfter.ToString("o")
        CerPath          = $rootCerPath
        CrtPath          = $rootCrtPath
        PfxPath          = $rootPfxPath
    }
    CodeSign = [PSCustomObject]@{
        Subject          = $codeSignCert.Subject
        Issuer           = $codeSignCert.Issuer
        Thumbprint       = $codeSignCert.Thumbprint
        SerialNumber     = $codeSignCert.SerialNumber
        NotBefore        = $codeSignCert.NotBefore.ToString("o")
        NotAfter         = $codeSignCert.NotAfter.ToString("o")
        CerPath          = $codeSignCerPath
        CrtPath          = $codeSignCrtPath
        PfxPath          = $codeSignPfxPath
    }
}

$metadata | ConvertTo-Json -Depth 5 | Set-Content -Path $metaJsonPath -Encoding UTF8

Write-Host "==========================================================" -ForegroundColor Green
Write-Host " [SUCCESS] Certificates successfully generated & exported!" -ForegroundColor Green
Write-Host " Root CA:        $rootCerPath" -ForegroundColor White
Write-Host " CodeSign PFX:   $codeSignPfxPath" -ForegroundColor White
Write-Host " CodeSign CER:   $codeSignCerPath" -ForegroundColor White
Write-Host " Metadata:       $metaJsonPath" -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Green

return $metadata
