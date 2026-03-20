# 15-Minute Path

Use this guide when you want one continuous path from first run to training
export.

By the end of this path you will have:

- validated ClawGraph locally
- connected the proxy shape you need for a real runtime
- checked builder-specific readiness
- exported a first dataset manifest

## Step 1. Validate the loop locally

Install ClawGraph and seed one complete session:

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

What this gives you:

- a complete OpenClaw-style session
- one declared retry branch
- score and preference artifacts
- a dry-run export preview

If this is your first time with ClawGraph, read the full
[Quickstart](./quickstart.md) after this step.

## Step 2. Connect a real OpenClaw-style runtime

Start with transparent proxy mode:

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

Then add stable ids in the runtime:

- `x-clawgraph-session-id`
- `x-clawgraph-run-id`
- `x-clawgraph-request-id`
- `x-clawgraph-user-id`

Add semantic events only where they improve training fidelity:

- `retry_declared`
- `fallback_declared`
- `controller_route_decided`

Use the full [OpenClaw Integration](./openclaw_integration.md) guide if you are
deciding how much runtime structure to add.

## Step 3. Turn captured runs into training data

For a newly captured session without artifacts, bootstrap supervision first:

```bash
clawgraph artifact bootstrap --template openclaw-defaults --session latest --dry-run
clawgraph artifact bootstrap --template openclaw-defaults --session latest
```

Then inspect readiness and export:

```bash
clawgraph readiness --session latest --builder sft
clawgraph readiness --session latest --builder preference
clawgraph readiness --session latest --builder binary_rl

clawgraph export dataset --builder preference --session latest --dry-run
clawgraph export dataset --builder preference --session latest --out out/preference.jsonl
```

If you need the full builder model and heuristics, read
[Dataset Builders](./dataset_builders.md).

## What to do next

- If you want a gentler first read, go to [Start Here](./start_here.md).
- If you want the shortest local validation, use [Quickstart](./quickstart.md).
- If you want to debug replay quality before export, use
  [Replay and Debug](./replay_and_debug.md).
- If you want downstream training handoff, continue with
  [Export to Async RL](./export_to_async_rl.md).
