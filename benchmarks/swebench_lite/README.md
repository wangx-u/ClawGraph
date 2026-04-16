# SWE-bench Lite With Generic Proxy Capture

This is the recommended way to validate ClawGraph with `SWE-bench Lite` and
`mini-SWE-agent`:

1. one terminal runs `clawgraph proxy`
2. one terminal runs the benchmark agent
3. the agent points its OpenAI-compatible model endpoint at the proxy
4. ClawGraph stays generic and only does capture, inspect, artifacts, curation,
   export, and evaluation planning

The important constraint is deliberate:

- no `mini-SWE-agent`-specific runtime shim inside ClawGraph
- no `SWE-bench`-specific ingestion path inside ClawGraph
- benchmark metadata should enter ClawGraph through the existing generic
  artifact model

## 1. Prepare `.venv`

```bash
cd clawgraph
bash benchmarks/swebench_lite/setup_env.sh
```

The setup script installs:

- `clawgraph` in editable mode
- `mini-swe-agent`
- `swebench`

If you want a Docker-free single-instance smoke run, you can also prepare a
local benchmark checkout:

```bash
./.venv/bin/python benchmarks/swebench_lite/prepare_local_instance.py \
  --instance sqlfluff__sqlfluff-1625 \
  --workdir /tmp/clawgraph-swebench/sqlfluff__sqlfluff-1625 \
  --python "$(pwd)/.venv/bin/python" \
  --install-editable \
  --force
```

This writes:

- `/tmp/clawgraph-swebench/sqlfluff__sqlfluff-1625/testbed`
- `/tmp/clawgraph-swebench/sqlfluff__sqlfluff-1625/.localenv`
- `/tmp/clawgraph-swebench/sqlfluff__sqlfluff-1625/mini.local.yaml`

You can then use that generated `mini.local.yaml` as an additional config layer
for `mini-extra swebench-single`.

The helper intentionally pins `setuptools<81` inside the local benchmark venv.
That keeps older repos that still import `pkg_resources` runnable during local
smoke validation.

## 1.1 One-shot phase-2 live validation

If you want one reusable command that exercises the generic phase-2 workflow
end to end, use:

```bash
DEEPSEEK_API_KEY=your-real-key \
bash benchmarks/swebench_lite/run_phase2_live_validation.sh
```

The script stays on the generic path:

- it starts or reuses a ClawGraph proxy
- it sends real OpenAI-compatible requests through the proxy
- it runs `clawgraph phase2 run`
- it lets phase 2 derive scorecard and promotion from the generic `score`
  artifacts already attached to the run, instead of hand-wiring benchmark-only
  evaluation logic
- it lets `mini-SWE-agent` generate live benchmark traffic through the same
  proxy
- it captures dashboard snapshots and the web bundle JSON that the UI consumes

If you already have a live proxy and store, reuse them instead of starting a
new proxy:

```bash
DEEPSEEK_API_KEY=your-real-key \
STORE_URI=sqlite:////tmp/clawgraph-phase2-final-live.db \
EXISTING_PROXY_BASE=http://127.0.0.1:8091 \
OUTPUT_DIR=/tmp/clawgraph-phase2-existing-report \
bash benchmarks/swebench_lite/run_phase2_live_validation.sh
```

The script writes all evidence to `OUTPUT_DIR`, including:

- `run1.initial.json`, `run1.rerun.json`
- `run2.initial.json`, `run2.rerun.json`
- `phase2.slice.json`
- `dashboard.before.json`, `dashboard.after.json`, `dashboard.watch.txt`
- `dashboard.bundle.json`
- `mini.live.traj.json` or `mini-standalone.traj.json`
- `summary.md`

## 1.2 Long-running benchmark collection

If you want to keep one proxy/store running and let multiple
`mini-SWE-agent` benchmark instances continuously accumulate into one
ClawGraph slice, use:

```bash
START_PROXY=0 \
PROXY_BASE=http://127.0.0.1:8092 \
STORE_URI=sqlite:////tmp/clawgraph-benchmark-collection.db \
OUTPUT_DIR=/tmp/clawgraph-benchmark-collection-out \
INSTANCE_PACK=diverse-lite \
bash benchmarks/swebench_lite/run_benchmark_collection.sh
```

This helper:

- reuses an ordinary ClawGraph proxy
- runs `mini-extra swebench-single` sequentially as an ordinary
  OpenAI-compatible client
- enriches completed runs through the generic artifact API
- runs `clawgraph phase2 run` for each run and again at slice scope
- exports dashboard snapshots and the same bundle consumed by the web UI

By default the collector now resolves a named instance pack instead of requiring
you to hand-maintain a comma-separated task list. The built-in packs are:

- `smoke`: one known-good issue for quick ingress checks
- `diverse-lite`: one issue from each cached repo family, suitable for product
  demos and pipeline validation
- `balanced-lite`: a slightly larger cross-repo set for longer accumulation
- `all-lite-dev`: the full cached `SWE-bench Lite` dev split

You can inspect the resolved pack before a run:

```bash
./.venv/bin/python benchmarks/swebench_lite/resolve_instance_pack.py \
  --pack diverse-lite \
  --format lines
```

Typical outputs in `OUTPUT_DIR`:

- one `*.traj.json`, `*.run.json`, `*.enrich.json`, and `*.phase2.json` per
  benchmark instance
- one per-run SFT export for each completed run
- one slice-level SFT export and manifest
- `dashboard.before.json`, `dashboard.after.json`, `dashboard.bundle.json`
- `final.slice.json`
- `summary.md`

The collector now auto-detects a cached local `SWE-Bench Lite` dataset and
switches to offline-cache mode when possible. That avoids long startup delays
caused by remote HuggingFace metadata probes during repeated validation runs.

## 1.3 Dashboard 联调与人工复核

如果你要按“用户视角”一起验证 proxy、agent 和 Dashboard，建议把 Web 页面也接到同一个
store：

```bash
cd clawgraph/web
NEXT_PUBLIC_DATA_MODE=prod \
CLAWGRAPH_STORE_URI=sqlite:////tmp/clawgraph-benchmark-collection.db \
CLAWGRAPH_PYTHON_BIN=/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/.venv/bin/python \
npm run dev -- --hostname 127.0.0.1 --port 3402
```

打开：

- `http://127.0.0.1:3402/`
- `http://127.0.0.1:3402/access`
- `http://127.0.0.1:3402/datasets/<snapshotId>`
- `http://127.0.0.1:3402/evaluation/<suiteId>`
- `http://127.0.0.1:3402/feedback`

当前 Dashboard 的对外口径已经统一为：

- `请求归属清晰度`
- `任务标签覆盖率`
- `决策语义覆盖率`
- `已生成验证资产`

不再使用容易误导的旧说法，例如“任务识别清晰度”或“可评估运行”。

页面展示也已经从“面向运维排查”收敛到“面向用户理解”：

- session / run 默认展示任务标题、仓库名和实例摘要，原始 `sess_xxx` /
  `run_xxx` 只作为次要标识
- replay / access 页会优先展示步骤类型和摘要，例如 `模型推理`、`工具调用`、
  `运行时事件`
- 原始接口路径如 `/chat/completions` 只保留为次级技术细节，不再作为主标题

在 `local-store` 模式下，`/feedback` 页面可以直接完成：

- `人工确认并入池`
- `标记已人工确认`
- `关闭当前事项`

这三类操作会通过通用 artifact / feedback 路径回写同一份 store，不依赖 benchmark
专用 API。

## 2. Terminal A: start ClawGraph proxy

Point the proxy at your real LLM upstream:

```bash
./.venv/bin/clawgraph proxy \
  --model-upstream https://your-openai-compatible-endpoint/v1/chat/completions \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db
```

ClawGraph is the generic capture layer here. It does not know or care whether
the caller is `mini-SWE-agent`, another coding agent, or an internal benchmark
harness, as long as the caller speaks an OpenAI-compatible HTTP surface.

## 3. Terminal B: point `mini-SWE-agent` at the proxy

Use the provided config template:

```bash
cp benchmarks/swebench_lite/mini_swe_agent.proxy.yaml /tmp/mini.proxy.yaml
```

Then edit only the model name if needed.

Minimal template:

```yaml
model:
  model_name: "gpt-4o-mini"
  cost_tracking: "ignore_errors"
  model_kwargs:
    custom_llm_provider: "openai"
    api_base: "http://127.0.0.1:8080"
    drop_params: true
```

`cost_tracking: "ignore_errors"` is intentional. It avoids false-negative
benchmark failures when the upstream model is OpenAI-compatible but not present
in LiteLLM's built-in cost registry.

Now run `mini-SWE-agent` or `mini-extra swebench` as usual, but with the proxy
config:

```bash
./.venv/bin/mini-extra swebench \
  --subset lite \
  --split dev \
  --workers 1 \
  --config /tmp/mini.proxy.yaml \
  --model gpt-4o-mini \
  --output tmp/swebench-lite
```

This keeps the architecture clean:

- `mini-SWE-agent` remains an ordinary OpenAI-compatible client
- `clawgraph proxy` remains an ordinary OpenAI-compatible capture layer
- the benchmark run naturally produces ClawGraph facts because the model traffic
  passes through the proxy

## 3.1 Terminal C: start the Dashboard against the same store

如果你希望边跑 benchmark 边看数据变化，可以单独开一个终端启动 Dashboard：

```bash
cd clawgraph/web
NEXT_PUBLIC_DATA_MODE=prod \
CLAWGRAPH_STORE_URI=sqlite:///../benchmarks/swebench_lite/clawgraph.db \
CLAWGRAPH_PYTHON_BIN=/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/.venv/bin/python \
npm run dev -- --hostname 127.0.0.1 --port 3402
```

推荐观察顺序：

1. `/access` 看真实请求是否进入同一 session / run
2. `/` 看 `任务标签覆盖率`、`决策语义覆盖率` 和 `已生成验证资产`
3. `/feedback` 处理需要人工确认的低置信样本
4. `/datasets/:snapshotId` 与 `/evaluation/:suiteId` 检查真实 manifest 和验证资产

For a local single-instance smoke run without Docker:

```bash
OPENAI_API_KEY=clawgraph-local \
./.venv/bin/mini-extra swebench-single \
  --subset lite \
  --split dev \
  --instance sqlfluff__sqlfluff-1625 \
  --model deepseek-chat \
  --config ./.venv/lib/python3.12/site-packages/minisweagent/config/benchmarks/swebench.yaml \
  --config benchmarks/swebench_lite/mini_swe_agent.proxy.yaml \
  --config /tmp/clawgraph-swebench/sqlfluff__sqlfluff-1625/mini.local.yaml \
  --yolo \
  --exit-immediately \
  --output /tmp/sqlfluff__sqlfluff-1625.traj.json
```

If your environment has never run `mini-SWE-agent`, initialize its one-time
local config first:

```bash
./.venv/bin/mini-extra config set MSWEA_CONFIGURED true
./.venv/bin/mini-extra config set MSWEA_MODEL_NAME openai/gpt-4o-mini
```

## 4. Inspect captured sessions

After the benchmark sends traffic, inspect it with existing ClawGraph commands:

```bash
./.venv/bin/clawgraph list sessions \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db

./.venv/bin/clawgraph inspect session \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db \
  --session latest

./.venv/bin/clawgraph list runs \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db \
  --session latest

./.venv/bin/clawgraph replay \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db \
  --session latest
```

## 5. Stay generic when attaching benchmark metadata

If you want benchmark verdicts or task metadata inside ClawGraph, use the
existing generic artifact interface instead of adding benchmark-specific code.

### Option A: use built-in bootstrap only

This is the lowest-friction path and is enough to validate the generic
capture-to-export loop:

```bash
./.venv/bin/clawgraph artifact bootstrap \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db \
  --session latest \
  --template openclaw-defaults

./.venv/bin/clawgraph readiness \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db \
  --session latest \
  --builder sft
```

This proves:

- proxy capture
- inspect and replay
- artifact derivation
- readiness checks
- dataset export planning

### Option B: append benchmark-aware artifacts through the generic API

If you want ClawGraph to remember the actual `SWE-bench` instance id or local
evaluation verdict, append them as ordinary artifacts.

Example E1 annotation payload:

```json
{
  "annotation_kind": "e1",
  "task_family": "swebench",
  "task_type": "issue_fix",
  "task_template_hash": "replace-with-stable-template-hash",
  "task_instance_key": "sympy__sympy-20590",
  "verifier_name": "swebench.resolved.v1",
  "verifier_score": 1.0,
  "quality_confidence": 0.95,
  "taxonomy_version": "clawgraph.swebench.v1",
  "annotation_version": "clawgraph.e1.swebench.v1",
  "source_channel": "benchmark.swebench_lite"
}
```

Append it with the generic CLI:

```bash
./.venv/bin/clawgraph artifact append \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db \
  --session latest \
  --run-id <run-id> \
  --type annotation \
  --target-ref run:<run-id> \
  --producer swebench.eval \
  --payload @annotation.json
```

If you have a resolved or unresolved verdict, attach it as a normal score:

```bash
./.venv/bin/clawgraph artifact append \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db \
  --session latest \
  --run-id <run-id> \
  --type score \
  --target-ref run:<run-id> \
  --producer swebench.eval \
  --payload '{"score": 1.0, "label": true, "outcome": "resolved"}'
```

That is enough to unlock the normal ClawGraph flow without any benchmark-only
logic in the codebase.

## 6. Validate readiness and export

Once artifacts exist, the rest is the standard ClawGraph flow:

```bash
./.venv/bin/clawgraph readiness \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db \
  --session latest \
  --builder sft

./.venv/bin/clawgraph readiness \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db \
  --session latest \
  --builder binary_rl

./.venv/bin/clawgraph export dataset \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db \
  --builder sft \
  --session latest \
  --out out/swebench_lite.sft.jsonl
```

If you appended benchmark verdicts as `score` artifacts, `binary_rl` can use
the same generic path:

```bash
./.venv/bin/clawgraph export dataset \
  --store sqlite:///benchmarks/swebench_lite/clawgraph.db \
  --builder binary_rl \
  --session latest \
  --out out/swebench_lite.binary_rl.jsonl
```

## 7. Recommended mental model

For this setup, keep the boundary sharp:

- `mini-SWE-agent` is only the caller
- `SWE-bench Lite` is only the workload source
- `clawgraph proxy` is only the generic evidence layer
- task labeling, cohort freezing, export, and offline evaluation all happen
  through ClawGraph's existing generic commands
