#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STORE_URI="${CLAWGRAPH_E2E_STORE_URI:-sqlite:////tmp/clawgraph-e2e.db}"
PORT="${PORT:-3410}"

PYTHON_BIN="${CLAWGRAPH_PYTHON_BIN:-$ROOT_DIR/../.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

python3 "$ROOT_DIR/scripts/seed_e2e_store.py" --store "$STORE_URI"

export NEXT_PUBLIC_DATA_MODE="prod"
export CLAWGRAPH_STORE_URI="$STORE_URI"
export CLAWGRAPH_PYTHON_BIN="$PYTHON_BIN"

cd "$ROOT_DIR"
exec npm run dev -- --hostname 127.0.0.1 --port "$PORT"
