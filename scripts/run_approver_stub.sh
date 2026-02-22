#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src"
python -m aimxs_approver_stub.stub --config config/prototype.local.yaml "$@"
