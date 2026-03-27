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
