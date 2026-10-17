# ==============================================================================
# Isolated Podman Build Automation Makefile
# All compilations, packaging, and dependency downloads occur strictly
# inside containers. Host environment remains pristine.
# ==============================================================================

IMAGE_LINUX := vpn-builder-linux
IMAGE_WINDOWS := vpn-builder-windows
WORKSPACE_DIR := $(shell pwd)

.PHONY: all help build-linux build-windows clean

all: help

help:
	@echo "Available commands:"
	@echo "  make build-linux    - Build standalone Linux executable in Podman"
	@echo "  make build-windows  - Build standalone Windows .exe in Podman (via Wine)"
	@echo "  make clean          - Remove generated artifacts and temp directories"

build-linux:
	@echo "==> Building Linux builder image..."
	podman build -t $(IMAGE_LINUX) -f Containerfile.build .
	@echo "==> Running isolated Linux build..."
	podman run --cgroups=disabled --rm -v "$(WORKSPACE_DIR):/workspace:Z" $(IMAGE_LINUX)

build-windows:
	@echo "==> Building Windows builder image..."
	podman build -t $(IMAGE_WINDOWS) -f docker/Containerfile.windows .
	@echo "==> Running isolated Windows build..."
	podman run --cgroups=disabled --rm -v "$(WORKSPACE_DIR):/workspace:Z" $(IMAGE_WINDOWS)

clean:
	@echo "==> Cleaning up dist and temporary folders..."
	rm -rf dist build *.spec
