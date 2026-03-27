# Export to Async RL

Use this guide when you already have captured runs and need a clean file-based
handoff into async RL, distillation, or evaluation stacks.

## Handoff boundary

ClawGraph should stay loosely coupled from the downstream trainer.

The intended boundary is:

- ClawGraph captures and structures execution
- downstream systems consume exported datasets and lineage records from files

That means the downstream trainer should not need to reopen the ClawGraph store
to hydrate training records.

## Smallest reliable handoff flow

```bash
clawgraph list sessions
clawgraph list runs --session latest

clawgraph artifact bootstrap --template openclaw-defaults --session latest --dry-run
clawgraph artifact bootstrap --template openclaw-defaults --session latest

clawgraph readiness --session latest --builder preference
clawgraph export dataset --builder preference --session latest --dry-run
clawgraph export dataset --builder preference --session latest --out out/preference.jsonl
```

Use this order:

1. inspect the session and choose the run you actually want to export
2. bootstrap supervision if facts exist but artifacts do not
3. check builder-specific readiness
4. dry-run export before writing files
5. hand downstream both the `*.jsonl` output and its manifest

## Export families you will use most

Typical export families:

- SFT samples
- preference pairs
- binary RL tuples
- teacher-target manifests
- lineage-aware export records

Current built-in builders:

- `sft`
- `preference`
- `binary_rl`

Each export writes:

- one `*.jsonl`
- one `*.jsonl.manifest.json`
- self-contained records with prompt, trajectory or completion, supervision payloads, and lineage

## Scope defaults that matter

- inspect and replay workflows stay session-oriented first
- export workflows default to the latest run inside the chosen session
- if one session contains multiple runs, use `clawgraph list runs --session <id>` and pass `--run-id` when you need an exact export target

## Best next pages

- read [Dataset Builders](./dataset_builders.md) for builder behavior and readiness heuristics
- use [`examples/export_to_async_rl`](../../examples/export_to_async_rl/README.md) for a runnable repository walkthrough
- use [CLI Reference](../reference/cli_reference.md) when you need exact export flags
