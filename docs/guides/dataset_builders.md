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
- each record includes a minimal `lineage` block
- `clawgraph export dataset --dry-run` previews record counts, blockers, and manifest metadata before writing files

Readiness uses the same builder logic as export:

- `clawgraph readiness --builder sft`
- `clawgraph readiness --builder preference`
- `clawgraph readiness --builder binary_rl`

Current builder inputs:

- `sft`: successful request/response pairs
- `preference`: active preference artifacts, ranking artifacts, or fallback branch-outcome heuristics
- `binary_rl`: active score/reward/label artifacts

Built-in supervision bootstrap:

- `clawgraph artifact bootstrap --template request-outcome-scores`
- `clawgraph artifact bootstrap --template branch-outcome-preference`
- `clawgraph artifact bootstrap --template openclaw-defaults`

## Smallest useful export flow

If you already have one captured session, the shortest reliable path is:

```bash
clawgraph artifact bootstrap --template openclaw-defaults --session latest --dry-run
clawgraph artifact bootstrap --template openclaw-defaults --session latest

clawgraph readiness --session latest --builder preference
clawgraph export dataset --builder preference --session latest --dry-run
clawgraph export dataset --builder preference --session latest --out out/preference.jsonl
```

Use this order:

1. bootstrap artifacts if the session has facts but no supervision
2. check builder-specific readiness
3. dry-run the export
4. write the JSONL and manifest

Next:

- return to [15-Minute Path](./fifteen_minute_path.md) for the full end-to-end guide
- read [Export to Async RL](./export_to_async_rl.md) for downstream handoff

Future families:

- OPD
- process RM
- branch comparison
