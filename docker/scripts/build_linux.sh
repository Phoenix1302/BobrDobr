#!/usr/bin/env bash
set -e

echo "=========================================================="
echo " Starting isolated Linux build inside Podman container..."
echo "=========================================================="

cd /workspace

# 1. Setup Python virtual environment
echo "[1/5] Setting up virtual environment..."
python3 -m venv /tmp/venv
source /tmp/venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 2. Check and prepare binary dependencies
echo "[2/5] Preparing binary dependencies..."
mkdir -p bin/linux dist/linux

# If amneziawg-go is missing, compile it from source using Go inside container
if [ ! -f "bin/linux/amneziawg-go" ]; then
    echo "amneziawg-go not found in bin/linux/. Compiling from source..."
    rm -rf /tmp/awg-src
    git clone --depth 1 https://github.com/amnezia-vpn/amneziawg-go.git /tmp/awg-src || true
    if [ -d "/tmp/awg-src" ]; then
        if (cd /tmp/awg-src && /usr/local/go/bin/go build -v -o /workspace/bin/linux/amneziawg-go .); then
            chmod +x bin/linux/amneziawg-go
            echo "Successfully built bin/linux/amneziawg-go"
        else
            echo "Warning: Go build failed. Binary can be provided manually."
        fi
    fi
fi

# Bundle system openconnect and vpnc-script if available
if [ -f "/usr/sbin/openconnect" ] && [ ! -f "bin/linux/openconnect" ]; then
    cp /usr/sbin/openconnect bin/linux/
    chmod +x bin/linux/openconnect
fi

if [ -f "/usr/share/vpnc-scripts/vpnc-script" ] && [ ! -f "bin/linux/vpnc-script" ]; then
    cp /usr/share/vpnc-scripts/vpnc-script bin/linux/
    chmod +x bin/linux/vpnc-script
fi

# 3. Compile standalone Linux executable with PyInstaller
echo "[3/5] Compiling application with PyInstaller..."
rm -rf /tmp/build

pyinstaller \
    --name=BobrDobr-VPN \
    --onefile \
    --windowed \
    --noconfirm \
    --clean \
    --paths=/workspace/src \
    --add-data="/workspace/src/gui:gui" \
    --add-data="/workspace/src/core:core" \
    --add-data="/workspace/src/utils:utils" \
    --add-data="/workspace/src/assets:assets" \
    --add-data="/workspace/bin/linux:bin/linux" \
    --distpath=/workspace/dist/linux \
    --workpath=/tmp/build \
    /workspace/src/main.py

chmod +x /workspace/dist/linux/BobrDobr-VPN

echo "[4/5] Verifying binary artifacts..."
ls -lh /workspace/dist/linux/BobrDobr-VPN

echo "[5/5] Build finished successfully!"
echo "Artifact generated at: dist/linux/BobrDobr-VPN"
