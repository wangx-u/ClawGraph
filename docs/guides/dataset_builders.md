# Dataset Builders

This guide is Step 3 of the [15-Minute Path](./fifteen_minute_path.md).

Dataset builders transform:

- trajectory views
- artifact views
- optional memory overlays
- selection filters

into reusable learning datasets.

Built-in families in ClawGraph:

- SFT
- preference
- binary RL

Current export behavior:

- every builder writes `*.jsonl`
- every export also writes `*.jsonl.manifest.json`
- each record is self-contained and includes prompt, trajectory or completion, and supervision payloads
- each record also includes a `lineage` block for traceability
- each export now generates a persisted `dataset_snapshot_id` and deterministic `train / val / test` split assignment
- `clawgraph export dataset --dry-run` previews record counts, blockers, split metadata, and snapshot manifest fields before writing files
- `clawgraph export dataset --cohort-id <id>` is the recommended path for repeated training exports

Scope reminder:

- inspect and replay workflows stay session-oriented first
- readiness and artifact bootstrap still start from session/run scope
- repeated export should move from run scope to registered `slice` and frozen `cohort`

Readiness uses the same builder logic as export:

- `clawgraph readiness --builder sft`
- `clawgraph readiness --builder preference`
- `clawgraph readiness --builder binary_rl`

Current builder inputs:

- `sft`: successful request/response pairs with normalized message history
- `preference`: active preference artifacts, ranking artifacts, or fallback branch-outcome heuristics, exported with branch trajectories
- `binary_rl`: active score/reward/label artifacts, exported with resolved request or branch context when available

Built-in supervision bootstrap:

- `clawgraph artifact bootstrap --template request-outcome-scores`
- `clawgraph artifact bootstrap --template branch-outcome-preference`
- `clawgraph artifact bootstrap --template openclaw-defaults`

## Recommended export flow

If you already have captured sessions, the recommended path is:

```bash
clawgraph artifact bootstrap --template openclaw-defaults --session latest --dry-run
clawgraph artifact bootstrap --template openclaw-defaults --session latest

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
clawgraph export dataset --builder preference --cohort-id <cohort-id> --dry-run
clawgraph export dataset --builder preference --cohort-id <cohort-id> --out out/preference.jsonl
```

Use this order:

1. bootstrap artifacts if sessions have facts but no supervision
2. register the stable slice boundary
3. inspect the candidate pool before freezing
4. freeze a cohort so the export input is explicit
5. dry-run the export
6. write the JSONL and manifest

If you prefer runnable repository files for this flow, use
[`examples/export_to_async_rl`](../../examples/export_to_async_rl/README.md).

Next:

- return to [15-Minute Path](./fifteen_minute_path.md) for the full end-to-end guide
- read [Export to Async RL](./export_to_async_rl.md) for downstream handoff
- use [`examples/export_to_async_rl`](../../examples/export_to_async_rl/README.md) for a runnable repository walkthrough

Future families:

- OPD
- process RM
- branch comparison
