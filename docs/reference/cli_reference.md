# CLI Reference

## `clawgraph proxy`

Start the proxy server.

Captures:

- model traffic
- tool traffic
- streaming chunks
- request ids and timing fields

## `clawgraph replay`

Inspect a replay for one session or one run.

## `clawgraph branches`

Inspect branches for a session or run scope.

Shows:

- inferred versus declared source
- branch status
- parent branch
- request counts

## `clawgraph list sessions`

List known sessions in recency order.

## `clawgraph list requests`

List request spans for one session or one run.

## `clawgraph list facts`

List facts for one session or run with optional `--kind` or `--actor` filters.

## `clawgraph bootstrap openclaw`

Seed a first-run OpenClaw-style session into the store.

If `--session-id` is omitted, ClawGraph generates a unique seed session id.

## `clawgraph inspect session`

Inspect a learning-oriented session summary.

## `clawgraph inspect request`

Inspect one request span with timing and identity fields.

Useful flags:

- `--session`
- `--run-id`

## `clawgraph inspect branch`

Inspect one branch or list branch summaries.

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
- `session:latest`

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

## `clawgraph readiness`

Inspect whether a session is ready for:

- SFT
- preference learning
- binary RL

Useful flags:

- `--builder`
- `--json`
- `--run-id`

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

Current CLI surface:

- `src/clawgraph/cli/main.py`
