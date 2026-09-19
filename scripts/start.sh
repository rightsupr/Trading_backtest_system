#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python || ! -d frontend/node_modules ]]; then
  echo '请先运行 ./scripts/setup.sh 安装依赖。'
  exit 1
fi
exec .venv/bin/python scripts/dev.py
