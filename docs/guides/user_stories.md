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

1. Route model and tool traffic through `clawgraph proxy`.
2. Add `x-clawgraph-session-id`, `x-clawgraph-request-id`, and `x-clawgraph-user-id`.
3. Use `clawgraph inspect session --session latest`.
4. Drill into one request with `clawgraph inspect request --request-id <id>`.

## 2. RL engineer

You want the same real run to support:

- SFT
- binary RL
- preference learning
- judge reruns

Typical workflow:

1. Capture runs once through the proxy.
2. Attach supervision with `clawgraph artifact append`.
3. Check `clawgraph readiness --session latest`.
4. Export only when the session is ready for the target builder.

## 3. Evaluator

You want to re-score old trajectories without mutating their source facts.

Typical workflow:

1. Replay the session with `clawgraph replay --session <id>`.
2. Append new scores or rankings as artifacts.
3. List active artifacts with `clawgraph artifact list --latest-only`.
4. Compare derived readiness before exporting.

## 4. Platform owner

You need a simple control-plane style answer:

- which sessions are export-ready
- which artifacts are active
- which branches are declared versus inferred

Typical workflow:

1. Inspect session summaries regularly.
2. Prefer declared semantic branches where fidelity matters.
3. Keep artifact status explicit: `active` versus `superseded`.
4. Use readiness output as the gate before builder export.
