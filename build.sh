#!/usr/bin/env bash
set -e

TARGET="${1:-linux}"

case "$TARGET" in
    linux)
        echo "==> Building Linux binary via Podman..."
        podman build -t vpn-builder-linux -f Containerfile.build .
        podman run --cgroups=disabled --rm -v "$(pwd):/workspace:Z" vpn-builder-linux
        echo "==> Done! Artifact: dist/linux/vpn-launcher"
        ;;
    windows)
        echo "==> Building Windows .exe via Podman (Wine)..."
        podman build -t vpn-builder-windows -f docker/Containerfile.windows .
        podman run --cgroups=disabled --rm -v "$(pwd):/workspace:Z" vpn-builder-windows
        echo "==> Done! Artifact: dist/windows/vpn-launcher.exe"
        ;;
    clean)
        echo "==> Cleaning dist/..."
        rm -rf dist build *.spec
        ;;
    *)
        echo "Usage: ./build.sh [linux|windows|clean]"
        exit 1
        ;;
esac
