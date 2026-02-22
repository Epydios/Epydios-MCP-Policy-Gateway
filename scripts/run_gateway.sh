#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src"
python3 -m aimxs_gateway.main --config config/prototype.local.yaml
