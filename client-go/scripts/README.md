# BobrDobr VPN - Code Signing & Packaging Scripts

This directory contains PowerShell automation scripts for the Authenticode Code Signing and Inno Setup packaging pipeline for **BobrDobr VPN**.

## Architecture Overview

```
                                  +-----------------------------+
                                  |    Generate-Certificate.ps1 |
                                  +--------------+--------------+
                                                 |
                                     Generates Root CA &
                                     Code Signing Certificate
                                                 |
                                                 v
                                  +-----------------------------+
                                  |    client-go/certs/         |
                                  | - BobrDobr-RootCA.cer       |
                                  | - BobrDobr-CodeSign.pfx     |
                                  +--------------+--------------+
                                                 |
             +-----------------------------------+-----------------------------------+
             |                                                                       |
             v                                                                       v
+-----------------------------+                                         +-----------------------------+
|    Install-Certificate.ps1  |                                         |       Sign-Binary.ps1       |
+--------------+--------------+                                         +--------------+--------------+
             |                                                                       |
Registers Root CA in Trusted Root                                        Signs executables & installer
Registers CodeSign in Trusted Publishers                                 with RFC 3161 Timestamping
             |                                                           (DigiCert / Sectigo)
             v                                                                       |
Windows Defender / SmartScreen:                                                      v
"Проверенный издатель: BobrDobr VPN"                                    +-----------------------------+
(Zero Unknown Publisher Warnings!)                                      |     Build-Installer.ps1     |
                                                                        +-----------------------------+
                                                                        Compiles Inno Setup 6 & Signs
```

---

## Scripts

### 1. `Generate-Certificate.ps1`
Generates a 2-tier PKI infrastructure:
1. **BobrDobr Root CA**: RSA 4096-bit self-signed root authority (`CN=BobrDobr Root CA, O=BobrDobr Hydro-engineering Team, C=RU`).
2. **BobrDobr Code Signing**: RSA 2048-bit certificate issued by Root CA with Code Signing EKU (`1.3.6.1.5.5.7.3.3`).

Exports:
- `client-go/certs/BobrDobr-RootCA.cer` (DER format) & `.crt` (PEM format)
- `client-go/certs/BobrDobr-CodeSign.cer` & `.crt`
- `client-go/certs/BobrDobr-CodeSign.pfx` (password protected)
- `client-go/certs/certificate-metadata.json`

**Usage:**
```powershell
powershell -ExecutionPolicy Bypass -File .\client-go\scripts\Generate-Certificate.ps1 -Force
```

---

### 2. `Sign-Binary.ps1`
Digitally signs executables (`.exe`), dynamic link libraries (`.dll`), and installer packages with Authenticode and RFC 3161 timestamping (DigiCert primary, Sectigo fallback).

**Key features:**
- Automatically detects `signtool.exe` or uses native PowerShell `Set-AuthenticodeSignature`.
- Connects to DigiCert RFC 3161 timestamp server so signatures remain valid forever even if the certificate expires.
- Verifies and prints full Authenticode signer and timestamp details.

**Usage:**
```powershell
# Sign a single executable
powershell -ExecutionPolicy Bypass -File .\client-go\scripts\Sign-Binary.ps1 -FilePath "dist\installer\BobrDobr-Setup.exe"

# Sign multiple binaries
powershell -ExecutionPolicy Bypass -File .\client-go\scripts\Sign-Binary.ps1 -FilePath "bin\windows\amneziawg-go.exe,bin\windows\openconnect-worker.exe"
```

---

### 3. `Install-Certificate.ps1`
Registers the BobrDobr Root CA and Code Signing certificate into Windows Certificate Stores:
- `Root` store: `Cert:\LocalMachine\Root` / `Cert:\CurrentUser\Root`
- `TrustedPublisher` store: `Cert:\LocalMachine\TrustedPublisher` / `Cert:\CurrentUser\TrustedPublisher`

Once installed:
- Windows Defender and SmartScreen display **"Проверенный издатель: BobrDobr Hydro-engineering Team"**
- Eliminates the red/orange "Windows protected your PC" / "Unknown Publisher" warnings completely.

**Usage:**
```powershell
# Standard user installation (registers TrustedPublisher)
powershell -ExecutionPolicy Bypass -File .\client-go\scripts\Install-Certificate.ps1

# Administrator installation (registers both LocalMachine\Root and LocalMachine\TrustedPublisher silently)
powershell -ExecutionPolicy Bypass -File .\client-go\scripts\Install-Certificate.ps1 -Elevate

# Clean up / remove certificates from stores
powershell -ExecutionPolicy Bypass -File .\client-go\scripts\Install-Certificate.ps1 -Uninstall
```

---

### 4. `Build-Installer.ps1`
End-to-end automation tool that:
1. Locates Inno Setup 6 (`ISCC.exe`).
2. Pre-signs application and backend binaries (`BobrDobr.exe`, `amneziawg-go.exe`, `openconnect-worker.exe`, `wintun.dll`).
3. Compiles `client-go/build/windows/installer/BobrDobr-Setup.iss` with ultra-compression (`lzma2/ultra64`).
4. Signs `BobrDobr-Setup.exe` with RFC 3161 timestamping.
5. Verifies Authenticode status and outputs SHA-256 hash.

**Usage:**
```powershell
powershell -ExecutionPolicy Bypass -File .\client-go\scripts\Build-Installer.ps1 -Version "1.3.0"
```
Output is placed in `dist/installer/BobrDobr-Setup.exe`.
