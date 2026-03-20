# Replay and Debug

ClawGraph replay is learning-oriented, not only operational.

Good replay should show:

- execution timeline
- branch tree
- retries and repairs
- artifact overlays
- ranking context
- export lineage

Replay should also surface:

- correlated request groups
- inferred retry branches
- attached external artifacts

This makes replay closer to a learning cockpit than a standard trace viewer.

Use replay together with:

- `clawgraph inspect session`
- `clawgraph inspect request`
- `clawgraph inspect branch`
- `clawgraph readiness --builder <builder>`
- `clawgraph export dataset --builder <builder> --dry-run`

Replay answers "what happened". Inspect and readiness answer "what is usable".
