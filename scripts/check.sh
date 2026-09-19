#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/ruff check backend
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build
