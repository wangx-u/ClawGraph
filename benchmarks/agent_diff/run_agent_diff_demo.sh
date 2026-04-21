#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CLAWGRAPH_DIR="$ROOT_DIR/clawgraph"
AGENT_DIFF_DIR="$ROOT_DIR/agent-diff"
OPS_DIR="$AGENT_DIFF_DIR/ops"
AGENT_DIFF_BASE_URL="${AGENT_DIFF_BASE_URL:-http://127.0.0.1:8000}"
AGENT_DIFF_BOOTSTRAP_MODE="${AGENT_DIFF_BOOTSTRAP_MODE:-docker}"
AGENT_DIFF_HEALTH_URL="${AGENT_DIFF_HEALTH_URL:-${AGENT_DIFF_BASE_URL%/}/api/platform/health}"

STORE_URI="${CLAWGRAPH_STORE_URI:-sqlite:////tmp/clawgraph-agent-diff-demo.db}"
PAYLOAD_DIR="${CLAWGRAPH_PAYLOAD_DIR:-/tmp/clawgraph-agent-diff-payloads}"
PROXY_HOST="${CLAWGRAPH_PROXY_HOST:-127.0.0.1}"
PROXY_PORT="${CLAWGRAPH_PROXY_PORT:-8093}"
PROXY_BASE_URL="${CLAWGRAPH_PROXY_BASE_URL:-http://${PROXY_HOST}:${PROXY_PORT}/v1}"
MODEL_UPSTREAM="${CLAWGRAPH_MODEL_UPSTREAM:-https://api.deepseek.com/v1/chat/completions}"
UPSTREAM_API_KEY="${CLAWGRAPH_UPSTREAM_API_KEY:-${DEEPSEEK_API_KEY:-}}"

if [[ -z "${UPSTREAM_API_KEY}" ]]; then
  echo "CLAWGRAPH_UPSTREAM_API_KEY or DEEPSEEK_API_KEY is required" >&2
  exit 1
fi

if ! curl -fsS "${AGENT_DIFF_HEALTH_URL}" >/dev/null 2>&1; then
  if [[ "${AGENT_DIFF_BOOTSTRAP_MODE}" == "docker" ]]; then
    cd "$OPS_DIR"
    docker compose up -d
  elif [[ "${AGENT_DIFF_BOOTSTRAP_MODE}" != "skip" ]]; then
    echo "Unsupported AGENT_DIFF_BOOTSTRAP_MODE=${AGENT_DIFF_BOOTSTRAP_MODE} (expected docker or skip)" >&2
    exit 1
  fi

  echo "waiting for agent-diff backend on ${AGENT_DIFF_BASE_URL} ..."
  for _ in $(seq 1 60); do
    if curl -fsS "${AGENT_DIFF_HEALTH_URL}" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
fi

if ! curl -fsS "${AGENT_DIFF_HEALTH_URL}" >/dev/null 2>&1; then
  echo "agent-diff backend did not become healthy on ${AGENT_DIFF_BASE_URL}" >&2
  if [[ "${AGENT_DIFF_BOOTSTRAP_MODE}" == "skip" ]]; then
    echo "Start agent-diff backend yourself, or rerun with AGENT_DIFF_BOOTSTRAP_MODE=docker" >&2
  fi
  exit 1
fi

cd "$CLAWGRAPH_DIR"

PROXY_PID=""
cleanup() {
  if [[ -n "${PROXY_PID}" ]] && kill -0 "${PROXY_PID}" >/dev/null 2>&1; then
    kill "${PROXY_PID}" >/dev/null 2>&1 || true
    wait "${PROXY_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if ! curl -fsS "${PROXY_BASE_URL%/v1}/healthz" >/dev/null 2>&1; then
  echo "starting clawgraph proxy on ${PROXY_BASE_URL} ..."
  ./.venv/bin/clawgraph proxy \
    --model-upstream "${MODEL_UPSTREAM}" \
    --store "${STORE_URI}" \
    --upstream-api-key "${UPSTREAM_API_KEY}" \
    --payload-dir "${PAYLOAD_DIR}" \
    --host "${PROXY_HOST}" \
    --port "${PROXY_PORT}" \
    >/tmp/clawgraph-agent-diff-proxy.log 2>&1 &
  PROXY_PID=$!
  for _ in $(seq 1 60); do
    if curl -fsS "${PROXY_BASE_URL%/v1}/healthz" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! curl -fsS "${PROXY_BASE_URL%/v1}/healthz" >/dev/null 2>&1; then
  echo "clawgraph proxy did not become healthy" >&2
  exit 1
fi

export CLAWGRAPH_STORE_URI="${STORE_URI}"
export CLAWGRAPH_PROXY_BASE_URL="${PROXY_BASE_URL}"
export AGENT_DIFF_BASE_URL="${AGENT_DIFF_BASE_URL}"

./.venv/bin/python benchmarks/agent_diff/run_agent_diff_demo.py "$@"

echo
echo "Dashboard command:"
echo "cd ${CLAWGRAPH_DIR}/web && NEXT_PUBLIC_DATA_MODE=prod CLAWGRAPH_STORE_URI=${STORE_URI} CLAWGRAPH_PYTHON_BIN=${CLAWGRAPH_DIR}/.venv/bin/python npm run dev -- --hostname 127.0.0.1 --port 3402"
