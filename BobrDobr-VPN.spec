# -*- mode: python ; coding: utf-8 -*-
import os

spec_dir = os.path.abspath(SPECPATH)

# Read APP_VERSION dynamically from version.py
app_version = "1.0.13"
version_file = os.path.join(spec_dir, "src", "utils", "version.py")
if os.path.isfile(version_file):
    try:
        with open(version_file, "r", encoding="utf-8") as vf:
            for line in vf:
                if line.startswith("APP_VERSION"):
                    app_version = line.split("=")[1].strip().strip('"').strip("'")
                    break
    except Exception:
        pass

exe_output_name = f"BobrDobr-VPN-v{app_version}"

a = Analysis(
    [os.path.join(spec_dir, 'src', 'main.py')],
    pathex=[os.path.join(spec_dir, 'src')],
    binaries=[],
    datas=[
        (os.path.join(spec_dir, 'src', 'gui'), 'gui'),
        (os.path.join(spec_dir, 'src', 'core'), 'core'),
        (os.path.join(spec_dir, 'src', 'utils'), 'utils'),
        (os.path.join(spec_dir, 'src', 'assets'), 'assets'),
        (os.path.join(spec_dir, 'bin', 'windows'), 'bin/windows'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# 1. Onedir launcher for installed system mode (runs directly from %LOCALAPPDATA%/Programs/BobrDobr without temp unpacking)
exe_installed = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BobrDobr-Installed',
    contents_directory='.',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(spec_dir, 'src', 'assets', 'beaver.ico')],
)

# 2. Standalone single-file executable for portable mode and distribution
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas + [('installed_launcher/BobrDobr-Installed.exe', exe_installed.name, 'DATA')],
    [],
    name=exe_output_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(spec_dir, 'src', 'assets', 'beaver.ico')],
)
