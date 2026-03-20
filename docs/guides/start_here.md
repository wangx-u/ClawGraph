# Start Here

If you are new to ClawGraph, start with the shortest path that matches your
goal.

## Fastest first run

Use this if you want to see the full loop locally before connecting a real
runtime.

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

- one complete OpenClaw-style session
- one declared retry branch
- ready-to-inspect artifacts
- a preview of what preference export would write

If you want one continuous guide from local validation to real runtime capture
and export, use [15-Minute Path](./fifteen_minute_path.md).

## Choose the path that matches your job

### I run an OpenClaw-style runtime

Start with:

- [Quickstart](./quickstart.md)
- [OpenClaw Integration](./openclaw_integration.md)
- [Proxy Mode](./proxy_mode.md)

Best next step:

- point your model and tool endpoints at `clawgraph proxy`
- add stable ids through headers
- add semantic events only for retry, fallback, and routing

### I need training data

Start with:

- [Dataset Builders](./dataset_builders.md)
- [Export to Async RL](./export_to_async_rl.md)
- [CLI Reference](../reference/cli_reference.md)

Best next step:

- inspect readiness by builder
- bootstrap supervision from captured runs
- export `sft`, `preference`, or `binary_rl`

### I need better debugging before training

Start with:

- [Replay and Debug](./replay_and_debug.md)
- [Branching](../concepts/branching.md)
- [Artifact Protocol](../concepts/artifact_protocol.md)

Best next step:

- inspect session, request, and branch views
- compare inferred and declared branches
- keep artifacts explicit and versioned

### I want the product mental model first

Start with:

- [What is ClawGraph](../overview/what_is_clawgraph.md)
- [Architecture](../overview/architecture.md)
- [Why Not Tracing](../overview/why_not_tracing.md)

## Recommended reading order

1. [15-Minute Path](./fifteen_minute_path.md)
2. [Quickstart](./quickstart.md)
3. [OpenClaw Integration](./openclaw_integration.md)
4. [User Stories](./user_stories.md)
5. [Dataset Builders](./dataset_builders.md)
6. [CLI Reference](../reference/cli_reference.md)

## Example catalog

Examples are organized by integration depth in [Examples](./examples.md).

If you are browsing the repository directly, the source files live under the
`examples/` directory.
