#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

STORE_BASENAME="${STORE_BASENAME:-clawgraph-swebench-collection-$(date +%s)}"
STORE_PATH="${STORE_PATH:-/tmp/${STORE_BASENAME}.db}"
STORE_URI="${STORE_URI:-sqlite:////${STORE_PATH#/}}"
PAYLOAD_DIR="${PAYLOAD_DIR:-/tmp/${STORE_BASENAME}-payloads}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/${STORE_BASENAME}-out}"
PREP_ROOT="${PREP_ROOT:-/tmp/clawgraph-swebench}"
INSTANCE_PACK="${INSTANCE_PACK:-diverse-lite}"
INSTANCE_IDS="${INSTANCE_IDS:-}"
PROXY_PORT="${PROXY_PORT:-8092}"
PROXY_BASE="${PROXY_BASE:-http://127.0.0.1:${PROXY_PORT}}"
START_PROXY="${START_PROXY:-1}"
USE_HF_OFFLINE_AUTO="${USE_HF_OFFLINE_AUTO:-1}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
PHASE2_OUTPUT_DIR="$OUTPUT_DIR/phase2"

mkdir -p "$OUTPUT_DIR" "$PAYLOAD_DIR" "$PHASE2_OUTPUT_DIR"

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

cleanup() {
  set +e
  if [[ -n "$PROXY_PID" ]] && kill -0 "$PROXY_PID" >/dev/null 2>&1; then
    kill "$PROXY_PID" >/dev/null 2>&1 || true
    wait "$PROXY_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

configure_dataset_access() {
  local hf_home cache_root
  hf_home="${HF_HOME:-$HOME/.cache/huggingface}"
  cache_root="${hf_home}/datasets/princeton-nlp___swe-bench_lite"
  if [[ "$USE_HF_OFFLINE_AUTO" == "1" && -d "$cache_root" ]]; then
    export HF_HUB_OFFLINE=1
    export HF_DATASETS_OFFLINE=1
    export CLAWGRAPH_BENCHMARK_DATASET_MODE="offline-cache"
    return 0
  fi
  export HF_HUB_ETAG_TIMEOUT="${HF_HUB_ETAG_TIMEOUT:-3}"
  export HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-10}"
  export CLAWGRAPH_BENCHMARK_DATASET_MODE="online"
}

configure_dataset_access
echo "Dataset access mode: ${CLAWGRAPH_BENCHMARK_DATASET_MODE}"

if [[ -z "$INSTANCE_IDS" ]]; then
  INSTANCE_IDS="$("$PYTHON_BIN" benchmarks/swebench_lite/resolve_instance_pack.py --pack "$INSTANCE_PACK")"
fi
echo "Benchmark instances: ${INSTANCE_IDS}"

wait_for_proxy() {
  local attempt
  for attempt in $(seq 1 30); do
    if curl -sS "${PROXY_BASE}/chat/completions" \
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

run_python() {
  PYTHONPATH=src "$PYTHON_BIN" "$@"
}

find_new_run() {
  local before_file="$1"
  local after_file="$2"
  run_python - "$STORE_URI" "$before_file" "$after_file" <<'PY'
import json
import sqlite3
import sys

store_uri = sys.argv[1]
before = set(json.loads(open(sys.argv[2], encoding="utf-8").read()))
after_hint = open(sys.argv[3], encoding="utf-8").read().strip()
db_path = store_uri.replace("sqlite:////", "/")
con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row
rows = con.execute(
    """
    select session_id, run_id, count(*) as fact_count, max(timestamp) as latest_ts
    from facts
    group by session_id, run_id
    order by latest_ts desc
    """
).fetchall()
best = None
for row in rows:
    if row["run_id"] in before:
        continue
    best = row
    break
if best is None:
    raise SystemExit("no new run detected")
print(json.dumps({
    "session_id": best["session_id"],
    "run_id": best["run_id"],
    "fact_count": best["fact_count"],
    "latest_ts": best["latest_ts"],
    "hint": after_hint,
}, ensure_ascii=False))
PY
}

snapshot_run_ids() {
  local output_file="$1"
  run_python - "$STORE_URI" "$output_file" <<'PY'
import json
import sqlite3
import sys

db_path = sys.argv[1].replace("sqlite:////", "/")
out_path = sys.argv[2]
con = sqlite3.connect(db_path)
rows = con.execute("select distinct run_id from facts order by run_id").fetchall()
with open(out_path, "w", encoding="utf-8") as handle:
    json.dump([row[0] for row in rows], handle)
PY
}

prepare_instance() {
  local instance_id="$1"
  local workdir="$PREP_ROOT/${instance_id}-prepared"
  if [[ -f "$workdir/instance.json" && -f "$workdir/mini.local.yaml" ]]; then
    return 0
  fi
  run_python benchmarks/swebench_lite/prepare_local_instance.py \
    --instance "$instance_id" \
    --workdir "$workdir" \
    --python "$PYTHON_BIN" \
    --install-editable
}

if [[ "$START_PROXY" == "1" ]]; then
  if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
    echo "DEEPSEEK_API_KEY is required when START_PROXY=1" >&2
    exit 1
  fi
  echo "Starting proxy on ${PROXY_BASE}"
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

run_python -m clawgraph.cli.main inspect dashboard \
  --store "$STORE_URI" \
  --json >"$OUTPUT_DIR/dashboard.before.json"

IFS=',' read -r -a instance_array <<<"$INSTANCE_IDS"
INSTANCE_COUNT="${#instance_array[@]}"
index=0
first_session=""
first_run=""
for instance_id in "${instance_array[@]}"; do
  index=$((index + 1))
  instance_id="$(echo "$instance_id" | xargs)"
  workdir="$PREP_ROOT/${instance_id}-prepared"
  prepare_instance "$instance_id"
  before_file="$OUTPUT_DIR/${instance_id}.before.json"
  after_hint_file="$OUTPUT_DIR/${instance_id}.hint.txt"
  traj_path="$OUTPUT_DIR/${instance_id}.traj.json"
  enrich_path="$OUTPUT_DIR/${instance_id}.enrich.json"
  phase2_path="$OUTPUT_DIR/${instance_id}.phase2.json"
  snapshot_run_ids "$before_file"
  date -u +"%Y-%m-%dT%H:%M:%SZ" >"$after_hint_file"
  echo "Running mini-SWE-agent for ${instance_id}"
  OPENAI_API_KEY=clawgraph-local ./.venv/bin/mini-extra swebench-single \
    --subset lite \
    --split dev \
    --instance "$instance_id" \
    --model deepseek-chat \
    --config ./.venv/lib/python3.12/site-packages/minisweagent/config/benchmarks/swebench.yaml \
    --config "$PROXY_CONFIG" \
    --config "$workdir/mini.local.yaml" \
    --yolo \
    --exit-immediately \
    --output "$traj_path" >"$OUTPUT_DIR/${instance_id}.mini.log" 2>&1

  run_meta="$(find_new_run "$before_file" "$after_hint_file")"
  session_id="$(echo "$run_meta" | "$PYTHON_BIN" -c 'import json,sys; print(json.loads(sys.stdin.read())["session_id"])')"
  run_id="$(echo "$run_meta" | "$PYTHON_BIN" -c 'import json,sys; print(json.loads(sys.stdin.read())["run_id"])')"
  if [[ -z "$first_session" ]]; then
    first_session="$session_id"
    first_run="$run_id"
  fi
  echo "$run_meta" >"$OUTPUT_DIR/${instance_id}.run.json"
  run_python benchmarks/swebench_lite/enrich_benchmark_run.py \
    --store "$STORE_URI" \
    --session-id "$session_id" \
    --run-id "$run_id" \
    --instance-json "$workdir/instance.json" \
    --traj-json "$traj_path" \
    --json >"$enrich_path"
  run_python -m clawgraph.cli.main phase2 run \
    --store "$STORE_URI" \
    --session "$session_id" \
    --run-id "$run_id" \
    --selection-scope run \
    --builder sft \
    --output-dir "$PHASE2_OUTPUT_DIR/$instance_id" \
    --json >"$phase2_path"
done

run_python -m clawgraph.cli.main phase2 run \
  --store "$STORE_URI" \
  --session "$first_session" \
  --run-id "$first_run" \
  --selection-scope slice \
  --builder sft \
  --holdout-fraction 0.34 \
  --create-eval-suite \
  --output-dir "$PHASE2_OUTPUT_DIR/final-slice" \
  --json >"$OUTPUT_DIR/final.slice.json"

run_python -m clawgraph.cli.main inspect dashboard \
  --store "$STORE_URI" \
  --json >"$OUTPUT_DIR/dashboard.after.json"

"$PYTHON_BIN" web/scripts/prod_dashboard_bundle.py \
  --store "$STORE_URI" \
  --session-limit 12 \
  --run-limit 32 \
  --artifact-limit 80 >"$OUTPUT_DIR/dashboard.bundle.json"

run_python - "$STORE_URI" "$OUTPUT_DIR" "${CLAWGRAPH_BENCHMARK_DATASET_MODE}" "$INSTANCE_PACK" "$INSTANCE_IDS" "$INSTANCE_COUNT" <<'PY'
import json
import sys
from pathlib import Path

store_uri = sys.argv[1]
out_dir = Path(sys.argv[2])
dataset_access_mode = sys.argv[3]
instance_pack = sys.argv[4]
instance_ids = [item.strip() for item in sys.argv[5].split(",") if item.strip()]
instance_count = sys.argv[6]
final_slice = json.loads((out_dir / "final.slice.json").read_text(encoding="utf-8"))
dashboard = json.loads((out_dir / "dashboard.after.json").read_text(encoding="utf-8"))
lines = [
    "# SWE-bench Collection Summary",
    "",
    f"- store: `{store_uri}`",
    f"- dataset_access_mode: `{dataset_access_mode}`",
    f"- instance_pack: `{instance_pack}`",
    f"- instance_count: `{instance_count}`",
    f"- instances: `{', '.join(instance_ids)}`",
    f"- slice: `{final_slice['slice']['record']['slice_id']}`",
    f"- training cohort: `{final_slice['training_cohort']['cohort_id']}`",
    f"- snapshots: `{dashboard['overview']['dataset_snapshots']}`",
    f"- captured sessions: `{dashboard['overview']['captured_sessions']}`",
    f"- captured runs: `{dashboard['overview']['captured_runs']}`",
    f"- e1 ready runs: `{dashboard['overview']['e1_ready_runs']}`",
    f"- export ready runs: `{dashboard['overview']['export_ready_runs']}`",
]
(out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo "Collection artifacts written to $OUTPUT_DIR"
