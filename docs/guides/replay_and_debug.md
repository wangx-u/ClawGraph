# Replay and Debug

ClawGraph replay is learning-oriented, not only operational.

Use replay before export whenever you need to answer whether the captured graph
matches what the runtime actually did.

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

## Smallest investigation flow

```bash
clawgraph inspect session --session latest
clawgraph list runs --session latest
clawgraph list requests --session latest
clawgraph inspect request --session latest --request-id latest
clawgraph replay --session latest
clawgraph inspect branch --session latest
clawgraph readiness --session latest --builder preference
clawgraph export dataset --builder preference --session latest --dry-run
```

Use this order:

1. inspect the session to confirm capture scope
2. inspect requests to find the failing or surprising step
3. replay the session to see branch structure and timing
4. inspect branches before deciding whether current artifacts are export-worthy
5. dry-run readiness or export only after replay looks correct

Use replay together with:

- `clawgraph inspect session`
- `clawgraph inspect request`
- `clawgraph inspect branch`
- `clawgraph readiness --builder <builder>`
- `clawgraph export dataset --builder <builder> --dry-run`

Replay answers "what happened". Inspect and readiness answer "what is usable".

## When to add more structure

- add stable headers when sessions or runs are hard to correlate
- add semantic events when inferred retry or fallback structure is wrong
- add artifacts when the execution is right but supervision is missing

## Best next pages

- [Proxy Mode](./proxy_mode.md)
- [Semantic Mode](./semantic_mode.md)
- [Artifact Protocol](../concepts/artifact_protocol.md)
