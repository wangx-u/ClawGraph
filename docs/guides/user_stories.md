# User Stories

ClawGraph is most useful when the user story is explicit.

## 1. Runtime engineer

You run an OpenClaw-style agent stack and need learning-grade observability
without rewriting the runtime.

Questions you need answered:

- which request actually failed
- whether the failure came from transport, model, tool, or fallback routing
- which branch was inferred and which branch was explicitly declared
- which request is slow enough to inspect in detail

Typical workflow:

1. Start with `clawgraph bootstrap openclaw` if you need a first-run baseline.
2. Route model and tool traffic through `clawgraph proxy` for real runtime capture.
3. Let ClawGraph auto-assign `session_id`, `run_id`, and `request_id` first.
4. Use `clawgraph inspect session --session latest`, `clawgraph list requests --session latest`, and `clawgraph replay --session latest`.
5. Add stable ids and semantic events only where replay grouping or branch fidelity needs to improve.

## 2. RL engineer

You want the same real run to support:

- SFT
- binary RL
- preference learning
- judge reruns

Typical workflow:

1. Bootstrap or capture runs once.
2. Discover sessions and requests with `clawgraph list`.
3. Use `clawgraph pipeline run --session latest --builder preference --dry-run` for one gated preview.
4. Run the same command without `--dry-run` to persist template artifacts and export in one pass.
5. Drop down to `artifact bootstrap`, `readiness`, and `export dataset` only when you need finer control.

## 3. Evaluator

You want to re-score old trajectories without mutating their source facts.

Typical workflow:

1. Replay the session with `clawgraph replay --session <id>`.
2. Resolve a target with `latest-response`, `latest-failed-branch`, or `session:latest`.
3. Use `clawgraph artifact bootstrap --template request-outcome-scores --session <id>` for a first pass.
4. Append new scores or rankings as artifacts only where the built-in template is not enough.
5. List active artifacts with `clawgraph artifact list --latest-only --session <id>`.
6. Compare derived readiness before exporting.

## 4. Platform owner

You need a simple control-plane style answer:

- which sessions are export-ready
- which artifacts are active
- which branches are declared versus inferred

Typical workflow:

1. Seed or capture sessions regularly.
2. Use `clawgraph list readiness --builder preference` to scan the most recent sessions first.
3. Inspect session summaries and branch sources where readiness is low or branch fidelity matters.
4. Prefer declared semantic branches where fidelity matters.
5. Keep artifact status explicit: `active` versus `superseded`.
6. Use `clawgraph pipeline run ... --dry-run` or `export dataset --dry-run` as the final gate before writing files.
