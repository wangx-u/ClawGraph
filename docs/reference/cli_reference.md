# CLI Reference

## `clawgraph proxy`

Start the proxy server.

Captures:

- model traffic
- tool traffic
- streaming chunks
- request ids and timing fields

## `clawgraph replay`

Inspect a session replay.

## `clawgraph branches`

Inspect branches for a session.

Shows:

- inferred versus declared source
- branch status
- parent branch
- request counts

## `clawgraph inspect session`

Inspect a learning-oriented session summary.

## `clawgraph inspect request`

Inspect one request span with timing and identity fields.

## `clawgraph inspect branch`

Inspect one branch or list branch summaries.

## `clawgraph semantic append`

Append a semantic runtime event.

## `clawgraph artifact append`

Append a typed external artifact with status, confidence, and supersession.

## `clawgraph artifact list`

List artifacts for a session or target with governance filters.

Filters:

- `--type`
- `--producer`
- `--version`
- `--status`
- `--latest-only`

## `clawgraph readiness`

Inspect whether a session is ready for:

- SFT
- preference learning
- binary RL

## `clawgraph export dataset`

Export a dataset with a selected builder.

Current CLI scaffold:

- [`src/clawgraph/cli/main.py`](../../src/clawgraph/cli/main.py)
