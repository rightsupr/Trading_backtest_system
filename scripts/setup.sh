#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 12), "请安装 Python 3.12+，或设置 PYTHON_BIN=/path/to/python3.12"'
command -v npm >/dev/null || { echo '请先安装 Node.js 20.19+ 或 22.12+'; exit 1; }
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
.venv/bin/python -m pip install --no-deps -e './backend[dev]'
npm --prefix frontend ci
echo '安装完成。运行 ./scripts/start.sh 启动前后端。'
