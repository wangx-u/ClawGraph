# Quickstart

This is the fastest way to see the full ClawGraph loop on your machine.

This guide is Step 1 of the [15-Minute Path](./fifteen_minute_path.md).

By the end of this guide you will have:

- one complete OpenClaw-style session with one run
- one declared retry branch
- inspectable artifacts
- a dry-run export preview

## 1. Install the package

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 2. Seed a first-run session

```bash
clawgraph bootstrap openclaw --store sqlite:///clawgraph.db
```

This writes a complete session with:

- one run
- request and response facts
- a declared retry branch
- a score artifact
- a preference artifact
- an E1 annotation artifact

If you prefer runnable repository files instead of a bootstrap command, use
[`examples/openclaw_quickstart`](../../examples/openclaw_quickstart/README.md).

## 3. Inspect what was created

```bash
clawgraph list sessions
clawgraph list runs --session latest
clawgraph list requests --session latest
clawgraph inspect request --session latest --request-id latest
clawgraph replay --session latest
clawgraph inspect branch --session latest
clawgraph readiness --session latest --builder preference
clawgraph export dataset --builder preference --session latest --dry-run
```

## 4. Export datasets

```bash
clawgraph export dataset --builder sft --session latest --out out/sft.jsonl
clawgraph export dataset --builder preference --session latest --out out/preference.jsonl
clawgraph export dataset --builder binary_rl --session latest --out out/binary_rl.jsonl
```

Each export also writes a manifest:

- `*.jsonl.manifest.json`

For a one-run bootstrap this direct export path is fine.

For repeated training exports, prefer:

```bash
clawgraph slice register --slice-id slice.capture \
  --task-family captured_agent_task \
  --task-type generic_proxy_capture \
  --taxonomy-version clawgraph.bootstrap.v1 \
  --sample-unit branch \
  --verifier-contract clawgraph.request_outcome_ratio.v1 \
  --risk-level medium \
  --default-use training_candidate \
  --owner ml-team
clawgraph slice candidates --slice-id slice.capture --min-quality-confidence 0.6
clawgraph cohort freeze --slice-id slice.capture --name capture-train
clawgraph export dataset --builder preference --cohort-id <cohort-id> --out out/preference.jsonl
```

## 5. Derive supervision for real captured sessions

If a session was captured through the proxy without artifacts yet:

```bash
clawgraph artifact bootstrap --template openclaw-defaults --session latest --dry-run
clawgraph artifact bootstrap --template openclaw-defaults --session latest
```

If your runtime emits stable run ids, the same commands also accept `--run-id <run>`.

## 6. Connect a real runtime later

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

For real runtime capture, the default path is now:

```bash
clawgraph proxy ...
clawgraph inspect session --session latest
clawgraph list runs --session latest
clawgraph replay --session latest
clawgraph pipeline run --session latest --builder preference --dry-run
```

You only need to add stable ids or semantic events later if replay grouping or
branch fidelity needs to improve.

Next:

- follow [15-Minute Path](./fifteen_minute_path.md) if you want a single capture-to-export flow
- read [OpenClaw Integration](./openclaw_integration.md) before wiring a real runtime
- read [Workflow Overview](./workflow_overview.md) for manual versus automated paths
- read [Dataset Builders](./dataset_builders.md) before exporting larger batches
- use [`examples/openclaw_quickstart`](../../examples/openclaw_quickstart/README.md) if you want the same flow as runnable repository files
