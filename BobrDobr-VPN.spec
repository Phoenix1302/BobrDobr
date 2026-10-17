# -*- mode: python ; coding: utf-8 -*-
import os

spec_dir = os.path.abspath(SPECPATH)

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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BobrDobr-VPN',
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
