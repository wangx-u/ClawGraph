# Custom Artifacts and Builders

Use this guide when the built-in templates and builders are not enough.

ClawGraph v1 is code-first. It does not require a complex DSL yet.

## Start with the lightest extension

Use the smallest extension that solves your problem:

- append a custom artifact if you already have an external judge, score, ranking, or label
- add a bootstrap template if the same artifact pattern should be derived repeatedly from facts
- add a dataset builder only when you need a new export family

## What already exists

- typed artifact records
- structured target shortcuts and selection filters
- built-in templates in `src/clawgraph/artifacts/templates.py`
- built-in builders in `src/clawgraph/export/dataset.py`

## Good extension points

- new artifact types appended through `clawgraph artifact append`
- new bootstrap templates when repeated supervision can be derived from facts
- new dataset builder cases when one new export family should become first-class
- custom manifests only when the downstream handoff needs extra metadata

## Minimum contract for a new builder

Keep the builder output aligned with the existing product boundary:

- write self-contained JSONL records
- include the prompt plus completion, trajectory, or target context needed for training
- include the supervision payload directly in each record
- include a `lineage` block for traceability
- stay run-oriented by default when one session contains multiple runs

## Suggested implementation order

1. prototype the supervision shape with `clawgraph artifact append`
2. verify target selection with `clawgraph artifact list` and `clawgraph readiness`
3. codify repeated artifact generation as a template
4. codify repeated export logic as a builder

## Good companion pages

- [Artifact Protocol](../concepts/artifact_protocol.md)
- [Dataset Builders](./dataset_builders.md)
- [CLI Reference](../reference/cli_reference.md)
