# Artifact Protocol

Artifacts are external, typed supervision objects attached to facts, sessions,
branches, or runs.

Examples:

- score
- label
- ranking
- critique
- constraint
- distillation target
- lineage

Artifacts exist so supervision can evolve without mutating historical facts.

Common artifact workflows include:

- append a score to `session:<id>`
- append a run-level reward or preference target to `run:<id>`
- attach a critique to `fact:<id>`
- attach a ranking to `branch:<id>`
- attach a distillation target to `fact:<id>` or `branch:<id>`

Governance fields in the current implementation:

- `status`: `active` or `superseded`
- `confidence`
- `supersedes_artifact_id`

This keeps judge reruns and reward revisions explicit instead of overwriting
old supervision.
