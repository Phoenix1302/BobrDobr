# BobrDobr VPN - Windows Packaging & Manifest

This directory contains the Windows Application Manifest and Inno Setup installer script for **BobrDobr VPN**.

## Directory Structure

```
client-go/build/
└── windows/
    ├── installer/
    │   ├── BobrDobr-Setup.iss       # Inno Setup 6 installer definition script
    │   └── Output/                  # Default output directory when compiled via IDE
    └── manifest/
        └── BobrDobr.exe.manifest    # Windows Application Manifest
```

---

## 1. Application Manifest (`manifest/BobrDobr.exe.manifest`)

The manifest configures Windows execution behavior:

- **Execution Level**: `<requestedExecutionLevel level="asInvoker" uiAccess="false"/>`
  Prevents unnecessary UAC elevation prompts during normal execution.
- **OS Compatibility GUIDs**:
  - Windows 10 & 11: `{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}`
  - Windows 8.1: `{4a2f28e3-53b9-4441-ba9c-d69d4a4a6e38}`
  - Windows 8: `{1f676c76-80e1-4239-95bb-83d0f6d0da78}`
  - Windows 7: `{35138b9a-5d96-4fbd-8e2d-a2440225f93a}`
- **High DPI Awareness**:
  - `dpiAware`: `true/pm`
  - `dpiAwareness`: `PerMonitorV2, PerMonitor` (crisp rendering across multi-monitor setups with different scaling factors).
- **Active Code Page**:
  - `activeCodePage`: `UTF-8` (modern Unicode standard without ANSI codepage translation issues).
- **Long Path Support**:
  - `longPathAware`: `true` (removes the MAX_PATH 260-character limitation).
- **Common Controls**:
  - Uses `Microsoft.Windows.Common-Controls` version 6.0.0.0 for modern Windows visual styles.

---

## 2. Inno Setup Script (`installer/BobrDobr-Setup.iss`)

Configured for seamless modern Windows software deployment:

- **Non-Elevated Installation**:
  - Target: `{localappdata}\Programs\BobrDobr`
  - `PrivilegesRequired=lowest` with `PrivilegesRequiredOverridesAllowed=dialog`.
  - Regular users can install without Administrator credentials, preventing permission locks.
- **Single-Instance Enforcement**:
  - Monitored mutex: `Global\BobrDobr_VPN_SingleInstance_Unified_v1`.
  - Checks during setup launch and during uninstallation, prompting the user to close any running instances.
- **Packaged Components**:
  - Main binary: `BobrDobr.exe`
  - Windows engines: `amneziawg-go.exe`, `openconnect-worker.exe`, `wintun.dll`.
  - Assets: `assets/bobr_logo.ico`, branding graphics, SVGs.
- **Shortcuts & Registry**:
  - Desktop shortcut (optional task) and Start Menu shortcut.
  - Optional Windows startup auto-launch via `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
  - Registration under Windows App Paths (`HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\BobrDobr.exe`).
- **Clean Uninstallation**:
  - Removes all installed program files, shortcuts, and registry keys.
  - Interactive prompt offering to completely wipe user cache, logs, and VPN profiles in `%LOCALAPPDATA%\BobrDobr`.

---

## Compiling the Installer

Use the automated script from `client-go/scripts/`:

```powershell
powershell -ExecutionPolicy Bypass -File .\client-go\scripts\Build-Installer.ps1 -Version "1.3.0"
```
