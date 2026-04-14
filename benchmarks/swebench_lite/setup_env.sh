#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${ROOT}/.venv/bin/python"

"${PYTHON_BIN}" -m ensurepip --upgrade
"${PYTHON_BIN}" -m pip install --upgrade pip
"${PYTHON_BIN}" -m pip install -e "${ROOT}"
"${PYTHON_BIN}" -m pip install mini-swe-agent swebench
