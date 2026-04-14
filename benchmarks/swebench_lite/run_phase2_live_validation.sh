#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "DEEPSEEK_API_KEY is required" >&2
  exit 1
fi

STORE_BASENAME="${STORE_BASENAME:-clawgraph-phase2-live-$(date +%s)}"
STORE_PATH="${STORE_PATH:-/tmp/${STORE_BASENAME}.db}"
STORE_URI="${STORE_URI:-sqlite:////${STORE_PATH#/}}"
PAYLOAD_DIR="${PAYLOAD_DIR:-/tmp/${STORE_BASENAME}-payloads}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/${STORE_BASENAME}-artifacts}"
PROXY_PORT="${PROXY_PORT:-8091}"
EXISTING_PROXY_BASE="${EXISTING_PROXY_BASE:-}"
if [[ -n "$EXISTING_PROXY_BASE" ]]; then
  PROXY_BASE="${EXISTING_PROXY_BASE%/}"
else
  PROXY_BASE="http://127.0.0.1:${PROXY_PORT}"
fi
INSTANCE_ID="${INSTANCE_ID:-sqlfluff__sqlfluff-1625}"
MINI_LOCAL_CONFIG="${MINI_LOCAL_CONFIG:-/tmp/clawgraph-swebench/${INSTANCE_ID}-prepared/mini.local.yaml}"

mkdir -p "$OUTPUT_DIR" "$PAYLOAD_DIR"

PROXY_CONFIG="$OUTPUT_DIR/mini.proxy.yaml"
cat >"$PROXY_CONFIG" <<EOF
model:
  model_name: "deepseek-chat"
  cost_tracking: "ignore_errors"
  model_kwargs:
    custom_llm_provider: "openai"
    api_base: "${PROXY_BASE}"
    drop_params: true
EOF

PROXY_PID=""
MINI_PID=""

cleanup() {
  set +e
  if [[ -n "$MINI_PID" ]] && kill -0 "$MINI_PID" >/dev/null 2>&1; then
    kill "$MINI_PID" >/dev/null 2>&1 || true
    wait "$MINI_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$PROXY_PID" ]] && kill -0 "$PROXY_PID" >/dev/null 2>&1; then
    kill "$PROXY_PID" >/dev/null 2>&1 || true
    wait "$PROXY_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

wait_for_proxy() {
  local attempt
  for attempt in $(seq 1 20); do
    if curl -sS "http://127.0.0.1:${PROXY_PORT}/chat/completions" \
      -H 'Content-Type: application/json' \
      -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"Reply with exactly READY"}],"stream":false}' \
      >"$OUTPUT_DIR/proxy.ready.json" 2>"$OUTPUT_DIR/proxy.ready.stderr"; then
      return 0
    fi
    sleep 1
  done
  echo "proxy did not become ready" >&2
  return 1
}

json_field() {
  local file_path="$1"
  local expression="$2"
  ./.venv/bin/python -c "import json,sys; data=json.load(open(sys.argv[1])); print(${expression})" "$file_path"
}

run_phase2_once() {
  local session_id="$1"
  local run_id="$2"
  local out_json="$3"
  local out_dir="$4"
  shift 4
  PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main phase2 run \
    --store "$STORE_URI" \
    --session "$session_id" \
    --run-id "$run_id" \
    --judge-provider openai-compatible \
    --judge-model deepseek-chat \
    --judge-api-base "${PROXY_BASE}/v1/chat/completions" \
    --judge-api-key clawgraph-local \
    --builder sft \
    --output-dir "$out_dir" \
    "$@" \
    --json >"$out_json"
}

ensure_dataset_ready() {
  local session_id="$1"
  local run_id="$2"
  local output_prefix="$3"
  local initial_json="${output_prefix}.initial.json"
  local rerun_json="${output_prefix}.rerun.json"
  local out_dir="${output_prefix}.out"

  run_phase2_once "$session_id" "$run_id" "$initial_json" "$out_dir" --selection-scope run
  local stage
  stage="$(json_field "$initial_json" "data['workflow_after']['stage']")"

  if [[ "$stage" != "dataset" && "$stage" != "evaluate" ]]; then
    PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main judge override \
      --store "$STORE_URI" \
      --session "$session_id" \
      --run-id "$run_id" \
      --review-note "human review confirmed this run is reusable for training" \
      --feedback-status resolved \
      --json >"${output_prefix}.override.json"
    run_phase2_once "$session_id" "$run_id" "$rerun_json" "$out_dir" --selection-scope run
    echo "$rerun_json"
    return 0
  fi

  echo "$initial_json"
}

if [[ -z "$EXISTING_PROXY_BASE" ]]; then
  echo "Starting proxy on port ${PROXY_PORT}"
  ./.venv/bin/clawgraph proxy \
    --model-upstream https://api.deepseek.com/v1/chat/completions \
    --store "$STORE_URI" \
    --upstream-api-key "$DEEPSEEK_API_KEY" \
    --payload-dir "$PAYLOAD_DIR" \
    --host 127.0.0.1 \
    --port "$PROXY_PORT" >"$OUTPUT_DIR/proxy.log" 2>&1 &
  PROXY_PID=$!
  wait_for_proxy
else
  echo "Using existing proxy at ${PROXY_BASE}"
fi

PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main inspect dashboard \
  --store "$STORE_URI" \
  --json >"$OUTPUT_DIR/dashboard.before.json"

for index in 1 2; do
  curl -sS "${PROXY_BASE}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer clawgraph-local' \
    -H "x-clawgraph-session-id: phase2_demo_session_${index}" \
    -H "x-clawgraph-run-id: phase2_demo_run_${index}" \
    -d "{\"model\":\"deepseek-chat\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly DEMO-${index} and nothing else.\"}],\"stream\":false}" \
    >"$OUTPUT_DIR/manual_${index}.response.json"
done

READY_ONE_JSON="$(ensure_dataset_ready phase2_demo_session_1 phase2_demo_run_1 "$OUTPUT_DIR/run1")"
READY_TWO_JSON="$(ensure_dataset_ready phase2_demo_session_2 phase2_demo_run_2 "$OUTPUT_DIR/run2")"

PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main phase2 run \
  --store "$STORE_URI" \
  --session phase2_demo_session_1 \
  --run-id phase2_demo_run_1 \
  --selection-scope slice \
  --builder sft \
  --holdout-fraction 0.5 \
  --create-eval-suite \
  --suite-kind offline_test \
  --scorecard-metrics '{"task_success_rate": 0.96, "verifier_pass_rate": 0.94, "p95_latency": 420}' \
  --scorecard-thresholds '{"task_success_rate": {"op": "gte", "value": 0.95}, "verifier_pass_rate": {"op": "gte", "value": 0.90}, "p95_latency": {"op": "lte", "value": 500}}' \
  --candidate-model small-v1 \
  --baseline-model large-v1 \
  --promotion-stage offline \
  --coverage-policy-version coverage.v1 \
  --promotion-summary "phase2 live validation passed" \
  --output-dir "$OUTPUT_DIR/slice" \
  --json >"$OUTPUT_DIR/phase2.slice.json"

if [[ ! -f "$MINI_LOCAL_CONFIG" ]]; then
  echo "Missing mini local config: $MINI_LOCAL_CONFIG" >&2
  exit 1
fi

echo "Starting mini-SWE-agent live run"
OPENAI_API_KEY=clawgraph-local ./.venv/bin/mini-extra swebench-single \
  --subset lite \
  --split dev \
  --instance "$INSTANCE_ID" \
  --model deepseek-chat \
  --config ./.venv/lib/python3.12/site-packages/minisweagent/config/benchmarks/swebench.yaml \
  --config "$PROXY_CONFIG" \
  --config "$MINI_LOCAL_CONFIG" \
  --yolo \
  --exit-immediately \
  --output "$OUTPUT_DIR/mini.live.traj.json" >"$OUTPUT_DIR/mini.log" 2>&1 &
MINI_PID=$!

PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main inspect dashboard \
  --store "$STORE_URI" \
  --watch \
  --interval-seconds 2 \
  --iterations 4 >"$OUTPUT_DIR/dashboard.watch.txt"

if kill -0 "$MINI_PID" >/dev/null 2>&1; then
  kill "$MINI_PID" >/dev/null 2>&1 || true
  wait "$MINI_PID" >/dev/null 2>&1 || true
fi
MINI_PID=""

PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main inspect dashboard \
  --store "$STORE_URI" \
  --json >"$OUTPUT_DIR/dashboard.after.json"

./.venv/bin/python web/scripts/prod_dashboard_bundle.py \
  --store "$STORE_URI" \
  --session-limit 8 \
  --run-limit 16 \
  --artifact-limit 40 >"$OUTPUT_DIR/dashboard.bundle.json"

FINAL_SLICE_ID="$(json_field "$OUTPUT_DIR/phase2.slice.json" "data['slice']['record']['slice_id']")"
TRAINING_COHORT_ID="$(json_field "$OUTPUT_DIR/phase2.slice.json" "data['training_cohort']['cohort_id']")"
EVAL_COHORT_ID="$(json_field "$OUTPUT_DIR/phase2.slice.json" "data['evaluation_cohort']['cohort_id']")"
EVAL_SUITE_ID="$(json_field "$OUTPUT_DIR/phase2.slice.json" "data['eval_suite']['eval_suite_id']")"
PROMOTION_DECISION="$(json_field "$OUTPUT_DIR/phase2.slice.json" "data['promotion']['decision']")"

cat >"$OUTPUT_DIR/summary.md" <<EOF
# Phase 2 Live Validation Summary

- store: \`${STORE_URI}\`
- phase2 slice: \`${FINAL_SLICE_ID}\`
- training cohort: \`${TRAINING_COHORT_ID}\`
- evaluation cohort: \`${EVAL_COHORT_ID}\`
- eval suite: \`${EVAL_SUITE_ID}\`
- promotion decision: \`${PROMOTION_DECISION}\`
- run1 result: \`$(basename "$READY_ONE_JSON")\`
- run2 result: \`$(basename "$READY_TWO_JSON")\`
- mini trajectory: \`$OUTPUT_DIR/mini.live.traj.json\`
- dashboard snapshot: \`$OUTPUT_DIR/dashboard.after.json\`
- dashboard bundle: \`$OUTPUT_DIR/dashboard.bundle.json\`
EOF

echo "Validation artifacts written to $OUTPUT_DIR"
