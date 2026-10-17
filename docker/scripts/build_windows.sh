#!/usr/bin/env bash
set -e

echo "=========================================================="
echo " Starting isolated Windows build in Wine Podman container..."
echo "=========================================================="

cd /workspace

mkdir -p bin/windows dist/windows

WINE_PYTHON="C:\\Python311\\python.exe"

# 1. Clean previous build caches and rotate running exe if locked
rm -rf /tmp/win_build
if [ -f "dist/windows/BobrDobr-VPN.exe" ]; then
    mv -f dist/windows/BobrDobr-VPN.exe dist/windows/BobrDobr-VPN.old 2>/dev/null || rm -f dist/windows/BobrDobr-VPN.exe 2>/dev/null || true
fi

# 1.1 Ensure multi-size Windows icon and checkmark assets are present
if [ ! -f "src/assets/beaver.ico" ] || [ ! -f "src/assets/check.png" ]; then
    echo "Generating beaver.ico and checkmark assets..."
    wine "$WINE_PYTHON" "Z:/workspace/scripts/generate_ico.py" || true
fi

# 2. Compile standalone Windows executable (.exe)
echo "[1/3] Compiling Windows .exe with BobrDobr beaver icon using PyInstaller..."
wine "$WINE_PYTHON" -m PyInstaller \
    --name=BobrDobr-VPN \
    --onefile \
    --windowed \
    --noconfirm \
    --clean \
    --icon="Z:/workspace/src/assets/beaver.ico" \
    --paths="Z:/workspace/src" \
    --add-data="Z:/workspace/src/gui;gui" \
    --add-data="Z:/workspace/src/core;core" \
    --add-data="Z:/workspace/src/utils;utils" \
    --add-data="Z:/workspace/src/assets;assets" \
    --add-data="Z:/workspace/bin/windows;bin/windows" \
    --distpath="Z:/workspace/dist/windows" \
    --workpath="C:/win_build" \
    "Z:/workspace/src/main.py"

wineserver -w

echo "[2/3] All binaries (AmneziaWG, OpenConnect, Wintun, DLLs) are packaged inside single-file executable."

echo "[3/3] Windows build complete!"
echo "Artifact generated at: dist/windows/BobrDobr-VPN.exe"
