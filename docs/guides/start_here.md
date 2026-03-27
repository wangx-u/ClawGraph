# Start Here

If you are new to ClawGraph, pick the next job you actually need to do.

ClawGraph is easiest to learn in three steps:

- validate one local run
- connect a real runtime
- export training data from captured runs

## 1. Validate one local run

Use this if you want one complete local loop before touching a real runtime.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

clawgraph bootstrap openclaw --store sqlite:///clawgraph.db
clawgraph inspect session --session latest
clawgraph replay --session latest
clawgraph readiness --session latest --builder preference
clawgraph export dataset --builder preference --session latest --dry-run
```

You will get:

- one complete OpenClaw-style session with one run
- one declared retry branch
- ready-to-inspect artifacts
- a preview of what preference export would write

Next:

- if you want a runnable repository example, open [`examples/openclaw_quickstart`](../../examples/openclaw_quickstart/README.md)
- if you want one continuous guide from local validation to export, use [15-Minute Path](./fifteen_minute_path.md)

## 2. Connect a real runtime

Use this if you already have an OpenClaw-style or OpenAI-compatible runtime and
want capture with minimal code changes.

Start with:

- [OpenClaw Integration](./openclaw_integration.md)
- [Proxy Mode](./proxy_mode.md)
- [Workflow Overview](./workflow_overview.md)

Recommended default:

- point model and tool endpoints at `clawgraph proxy`
- let ClawGraph auto-assign ids first
- inspect the session before adding more structure
- add stable ids only when replay grouping is weak
- add semantic events only for retry, fallback, and routing decisions

Best runnable examples:

- [`examples/openclaw_proxy_minimal`](../../examples/openclaw_proxy_minimal/README.md)
- [`examples/openclaw_python_helper`](../../examples/openclaw_python_helper/README.md)
- [`examples/openclaw_openai_wrapper`](../../examples/openclaw_openai_wrapper/README.md)

## 3. Export training data

Use this if you already have captured runs and need training-ready JSONL plus
manifest files.

Start with:

- [Dataset Builders](./dataset_builders.md)
- [Export to Async RL](./export_to_async_rl.md)
- [CLI Reference](../reference/cli_reference.md)

Recommended default:

- inspect the session first, then choose a run if there are multiple runs
- bootstrap built-in supervision before hand-authoring artifacts
- run `readiness` before `export dataset`
- use `pipeline run --dry-run` as the last gate before writing files

Best runnable example:

- [`examples/export_to_async_rl`](../../examples/export_to_async_rl/README.md)

## Keep this mental model

- `session` is the durable container
- `run` is one execution episode inside that session
- inspect and replay start from the session view
- readiness, bootstrap, pipeline, and export are run-oriented by default

## Use these as reference after the first run

- [Replay and Debug](./replay_and_debug.md) for investigation workflow
- [Examples](./examples.md) for runnable repository paths
- [User Stories](./user_stories.md) for role-specific flows
- [What is ClawGraph](../overview/what_is_clawgraph.md), [Architecture](../overview/architecture.md), and [Why Not Tracing](../overview/why_not_tracing.md) for product context
