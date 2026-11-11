#!/bin/sh
set -e

echo "=== Building OpenConnect Pure-Go CSTP Worker CLI for Windows x64 ==="

WORK_DIR="/workspace/openconnect-worker"
cd "$WORK_DIR"

export CGO_ENABLED=0
export GOOS=windows
export GOARCH=amd64

go build -ldflags="-s -w" -v -o /workspace/bin/windows/openconnect-worker.exe main.go

cp /workspace/bin/windows/openconnect-worker.exe /workspace/dist/windows/openconnect-worker.exe

echo "[+] openconnect-worker.exe successfully compiled and deployed to bin/windows/ and dist/windows/!"
