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
3. Add `x-clawgraph-session-id`, `x-clawgraph-run-id`, `x-clawgraph-request-id`, and `x-clawgraph-user-id`.
4. Use `clawgraph list requests --session latest` or `--run-id <run>`.
5. Drill into one request with `clawgraph inspect request --session latest --request-id latest`.

## 2. RL engineer

You want the same real run to support:

- SFT
- binary RL
- preference learning
- judge reruns

Typical workflow:

1. Bootstrap or capture runs once.
2. Discover sessions and requests with `clawgraph list`.
3. Start with `clawgraph artifact bootstrap --template openclaw-defaults --session latest --dry-run`.
4. Persist the template when the preview looks right.
5. Check `clawgraph readiness --session latest --builder preference` or scope to `--run-id`.
6. Use `clawgraph export dataset --builder preference --session latest --dry-run` before writing files.

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
2. Inspect session summaries and branch sources.
3. Prefer declared semantic branches where fidelity matters.
4. Keep artifact status explicit: `active` versus `superseded`.
5. Use `readiness --builder ...` plus `export dataset --dry-run`, scoped by session or run, as the gate before writing files.
