# Export to Async RL

Use this when you already have captured sessions and want training files that
downstream async RL or distillation systems can consume.

## Builders you will use most

- `sft`
- `preference`
- `binary_rl`

## Typical flow

1. Inspect a session or run.
2. Bootstrap or append supervision artifacts.
3. Check builder-specific readiness.
4. Run `clawgraph export dataset --dry-run`.
5. Write the export and its manifest.

## What you get

- builder-specific JSONL output
- a lineage-aware sidecar manifest
- a clean handoff point into downstream training stacks

This example covers:

- building an SFT dataset
- building a preference dataset
- building a binary RL dataset
- exporting lineage-aware manifests for downstream training
