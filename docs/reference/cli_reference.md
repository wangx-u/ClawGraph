# CLI Reference

Store URI examples:

- `sqlite:///clawgraph.db` writes `clawgraph.db` under the current working directory
- `sqlite:///tmp/clawgraph.db` writes to the absolute path `/tmp/clawgraph.db`

Scope model:

- `session`: durable container for related activity
- `run`: one execution episode inside a session
- `request` and `branch` live inside one run
- inspect and replay commands are session-oriented by default
- readiness, artifact bootstrap, pipeline, and export commands default to the latest run inside the selected session when `--run-id` is omitted

## `clawgraph proxy`

Start the proxy server.

Captures:

- model traffic
- tool traffic
- streaming chunks
- request ids and timing fields

Useful flags:

- `--model-upstream`
- `--tool-upstream`
- `--auth-token`
- `--upstream-api-key`
- `--store`

## `clawgraph replay`

Inspect a replay for one session or one run.

## `clawgraph branches`

Inspect branches for a session or run scope.

When `--run-id` is omitted, ClawGraph lists branches across the selected
session and includes `run_id` in the output.

Shows:

- inferred versus declared source
- branch status
- parent branch
- request counts

## `clawgraph list sessions`

List known sessions in recency order.

## `clawgraph list runs`

List known runs for one session in recency order.

## `clawgraph list requests`

List request spans for one session or one run.

When `--run-id` is omitted, ClawGraph lists requests across the selected
session.

## `clawgraph list facts`

List facts for one session or run with optional `--kind` or `--actor` filters.

When `--run-id` is omitted, ClawGraph lists facts across the selected session.

## `clawgraph list readiness`

List builder readiness across recent runs.

Each row reports the run used for evaluation.

Useful flags:

- `--builder`
- `--limit`
- `--json`

## `clawgraph bootstrap openclaw`

Seed a first-run OpenClaw-style session with one run into the store.

If `--session-id` is omitted, ClawGraph generates a unique seed session id.

## `clawgraph inspect session`

Inspect a learning-oriented session summary.

By default this inspects the full selected session. Use `clawgraph list runs`
and `--run-id` when you want one run only.

## `clawgraph inspect request`

Inspect one request span with timing and identity fields.

`--request-id latest` resolves within the selected session unless you also pass
`--run-id`.

Useful flags:

- `--session`
- `--run-id`

## `clawgraph inspect branch`

Inspect one branch or list branch summaries.

## `clawgraph inspect dashboard`

Inspect one dashboard-oriented snapshot that aggregates:

- session inbox state
- run-level evidence and learning readiness
- workflow-stage status, blockers, and next actions
- slice / cohort / dataset / eval governance state

Useful flags:

- `--builder`
- `--session-limit`
- `--run-limit`
- `--watch`
- `--interval-seconds`
- `--iterations`
- `--json`

## `clawgraph inspect workflow`

Inspect one run-scoped phase-2 workflow row.

This command uses the same stage logic as the dashboard and returns:

- `stage / stage_label`
- `trajectory_status`
- `review_status`
- `blockers`
- `review_reasons`
- `next_action`

Useful flags:

- `--session`
- `--run-id`
- `--builder`
- `--json`

## `clawgraph semantic append`

Append a semantic runtime event.

`--payload` accepts either inline JSON or `@path/to/file.json`.

## `clawgraph artifact append`

Append a typed external artifact with status, confidence, and supersession.

`--payload` accepts either inline JSON or `@path/to/file.json`.

Target shortcuts:

- `latest-response`
- `latest-failed-branch`
- `latest-succeeded-branch`
- `run:latest` for run-scoped supervision and export-oriented targets
- `session:latest` only when you intentionally want a session-scoped artifact

## `clawgraph artifact bootstrap`

Derive artifacts from built-in supervision templates.

Current templates:

- `request-outcome-scores`
- `branch-outcome-preference`
- `openclaw-defaults`

Useful flags:

- `--dry-run`
- `--json`
- `--producer`
- `--version`
- `--run-id`

If `--run-id` is omitted, ClawGraph uses the latest run inside the selected
session.

Repeated runs skip exact duplicate active artifacts for the same template output.

## `clawgraph artifact list`

List artifacts for a session or target with governance filters.

`--latest-only` keeps active, non-superseded artifacts while preserving
multiple distinct supervision records on the same session or branch.

Filters:

- `--type`
- `--producer`
- `--version`
- `--status`
- `--latest-only`
- `--run-id`

## `clawgraph judge annotate`

Plan or append one run-level E1 annotation produced by a generic judge.

Supported providers:

- `heuristic`
- `openai-compatible`

What it does:

- derives stable E1 defaults from the captured run
- optionally calls an OpenAI-compatible LLM judge
- appends one versioned annotation artifact
- keeps `review_reasons` and `supersedes_artifact_id` for later override

Useful flags:

- `--provider`
- `--model`
- `--api-base`
- `--api-key` or `--api-key-env`
- `--instructions`
- `--dry-run`
- `--json`

## `clawgraph judge override`

Append one manual override annotation for a run.

What it does:

- loads the current run-level annotation when available
- appends a superseding annotation artifact with producer like `human-review`
- can clear `review_reasons` and optionally resolve queued feedback items

Useful flags:

- `--payload`
- `--review-note`
- `--preserve-review-reasons`
- `--feedback-status reviewed|resolved`
- `--slice-id`
- `--reviewer`
- `--dry-run`
- `--json`

## `clawgraph readiness`

Inspect whether the selected run is ready for:

- SFT
- preference learning
- binary RL

Useful flags:

- `--builder`
- `--json`
- `--run-id`

If `--run-id` is omitted, ClawGraph evaluates the latest run inside the
selected session.

## `clawgraph feedback enqueue`

Append one feedback queue item by hand.

`--payload` accepts either inline JSON or `@path/to/file.json`.

## `clawgraph feedback list`

List feedback queue items, optionally filtered by `--slice-id` and `--status`.

## `clawgraph feedback sync`

Preview or append feedback queue items derived from one slice review queue.

What it does:

- resolves the slice candidate pool
- applies the same review thresholds used by curation
- appends deduplicated feedback items for flagged runs

Useful flags:

- `--slice-id`
- `--session`
- `--run-id`
- `--min-quality-confidence`
- `--min-verifier-score`
- `--dry-run`
- `--json`

## `clawgraph feedback resolve`

Mark feedback queue items as `reviewed` or `resolved`.

Selectors:

- `--feedback-id`
- `--target-ref`
- `--slice-id`

Useful flags:

- `--from-status`
- `--status`
- `--note`
- `--reviewer`
- `--json`

## `clawgraph pipeline run`

Plan or run a gated capture-to-export workflow for one session or run.

What it does:

- optionally derives built-in supervision artifacts
- computes builder-specific readiness on the staged result
- exports the dataset when the scope is ready

Useful flags:

- `--builder`
- `--template`
- `--skip-bootstrap`
- `--out`
- `--dry-run`
- `--run-id`

If `--run-id` is omitted, ClawGraph stages and evaluates the latest run inside
the selected session.

## `clawgraph export dataset`

Export a dataset with a selected builder.

Current built-in builders:

- `facts`
- `sft`
- `preference`
- `binary_rl`

Every export also writes a manifest next to the JSONL output.

Useful flags:

- `--dry-run`
- `--json`
- `--run-id`

If `--run-id` is omitted, ClawGraph exports the latest run inside the selected
session.

Current CLI surface:

- `src/clawgraph/cli/main.py`

## `clawgraph control-plane serve`

启动独立的 ClawGraph control-plane 服务，提供 Dashboard bundle、feedback mutation 和
training action 的 HTTP 入口。

典型用法：

```bash
clawgraph control-plane serve \
  --store sqlite:///clawgraph.db \
  --manifest-dir /tmp/clawgraph-manifests \
  --host 127.0.0.1 \
  --port 8787 \
  --auth-token your-token \
  --actor clawgraph.control_plane
```

Useful flags:

- `--store`
- `--manifest-dir`
- `--host`
- `--port`
- `--auth-token`
- `--actor`
- `--session-limit`
- `--run-limit`
- `--artifact-limit`

## `clawgraph logits doctor`

检查 Logits 集成的运行时契约是否完整。

会输出：

- 当前通过显式路径或可选 workspace auto-discovery 识别到的 workspace root
- `workspace_auto_discovery_enabled`
- `CLAWGRAPH_LOGITS_SRC`
- `CLAWGRAPH_LOGITS_COOKBOOK_SRC`
- `logits / logits_cookbook / tinker` 三个模块的可导入状态

当训练或评测桥报依赖缺失时，先运行：

```bash
clawgraph logits doctor --json
```

如果本地不是通过 pip 安装 `logits` / `logits-cookbook`，可以显式设置：

- `CLAWGRAPH_LOGITS_SRC=/abs/path/to/logits/src`
- `CLAWGRAPH_LOGITS_COOKBOOK_SRC=/abs/path/to/logits-cookbook`

如果只是本地开发临时复用同级 workspace，也可以显式开启：

- `CLAWGRAPH_ALLOW_WORKSPACE_LOGITS_DISCOVERY=1`

推荐先安装 ClawGraph 自己的 Logits 运行时补充依赖：

```bash
pip install -e '.[logits-runtime]'
```

说明：

- `logits-runtime` 目前只声明 ClawGraph 这侧可稳定声明的依赖，例如 `tinker`
- 生产和 CI 环境推荐使用已安装包或显式路径
- sibling workspace auto-discovery 默认关闭，只建议在本地开发时显式开启

## `clawgraph logits registry`

读取 store-backed 训练资产 registry，并可选从 manifest 目录补充尚未入库的资产。

会补的血缘包括：

- `training request -> model candidate`
- `model candidate -> eval execution`
- `model candidate -> router handoff`
- `dataset snapshot / eval suite / scorecard / promotion` 的真实标签补充

典型用法：

```bash
clawgraph logits registry \
  --store sqlite:///clawgraph.db \
  --json
```

Useful flags:

- `--manifest-dir`
- `--store`
- `--json`

## `clawgraph logits prepare-sft`

把一个 `sft` 数据快照转成 Logits 训练请求 manifest。

典型输入：

- `--dataset-snapshot-id`
- `--output-dir`
- `--base-model`

常用输出：

- conversation JSONL
- `logits_training_request` manifest

Useful flags:

- `--renderer-name`
- `--base-url`
- `--api-key-env`
- `--load-checkpoint-path`
- `--learning-rate`
- `--num-epochs`
- `--manifest-out`
- `--json`

## `clawgraph logits prepare-dpo`

把一个 `preference` 数据快照转成 Logits DPO 训练请求 manifest。

典型输入：

- `--dataset-snapshot-id`
- `--output-dir`
- `--base-model`

Useful flags:

- `--dpo-beta`
- `--learning-rate`
- `--num-epochs`
- `--manifest-out`
- `--json`

## `clawgraph logits prepare-rl`

生成一个环境驱动 RL 训练请求 manifest。

注意：

- 当前只负责 bridge 和 manifest，不自动构造 env
- `dataset_builder_ref` 必须指向一个可构造的数据构建器

Useful flags:

- `--dataset-builder-ref`
- `--dataset-builder-kwargs`
- `--slice-id`
- `--eval-suite-id`
- `--manifest-out`
- `--json`

## `clawgraph logits submit`

提交一个 `training request manifest`，产出 `model candidate manifest`。

说明：

- 默认会使用 manifest 中内建的 runtime 配置
- 也可以用 `--executor-ref` 指向外部提交器

Useful flags:

- `--manifest`
- `--executor-ref`
- `--candidate-out`
- `--json`

## `clawgraph logits evaluate`

让一个候选模型在冻结的 `eval suite` 上执行离线评测，并回写：

- `eval execution manifest`
- `scorecard`
- 可选的 `promotion decision`

当前边界：

- 当前内建评测桥稳定支持的是基于对话样本的 offline eval
- 更通用的 env / verifier 执行器仍属于后续扩展

Useful flags:

- `--candidate-manifest`
- `--eval-suite-id`
- `--baseline-model`
- `--grader`
- `--grader-ref`
- `--thresholds`
- `--record-promotion`
- `--promotion-stage`
- `--coverage-policy-version`
- `--rollback-conditions`
- `--json`

## `clawgraph logits handoff`

从 `promotion decision` 生成一份面向 router / serving 的交接 manifest。

Useful flags:

- `--candidate-manifest`
- `--promotion-decision-id`
- `--output`
- `--metadata`
- `--json`
