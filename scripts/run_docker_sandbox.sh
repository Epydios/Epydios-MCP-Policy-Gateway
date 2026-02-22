#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE_NAME="aimxs-mcp-gateway:v1"

docker build -t "$IMAGE_NAME" .

mkdir -p evidence demo_sandbox

# Run with hardened defaults:
# - no network
# - read-only rootfs
# - drop linux caps
# - no new privileges
# - tmpfs /tmp
# - bind-mount only evidence/ and demo_sandbox/ as writable
docker run --rm -i \
  --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 128 \
  --memory 512m \
  --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -p 8787:8787 \
  -v "$(pwd)/evidence:/app/evidence:rw" \
  -v "$(pwd)/demo_sandbox:/app/demo_sandbox:rw" \
  "$IMAGE_NAME"
