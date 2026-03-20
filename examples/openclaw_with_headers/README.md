# OpenClaw With Context Headers

Use this when you control runtime headers and want cleaner session and request
correlation.

## Recommended headers

- `x-clawgraph-session-id`
- `x-clawgraph-run-id`
- `x-clawgraph-request-id`
- `x-clawgraph-user-id`
- `x-clawgraph-parent-id`

## What you get

- stable request inspection
- cleaner branch grouping
- better readiness and export scoping
- easier user and run level debugging

## Best next step

If retries, fallbacks, or router decisions need to be explicit, move to
[`../openclaw_with_semantic_contract`](../openclaw_with_semantic_contract/README.md).

This example covers:

- transparent proxy capture
- stable header propagation
- better session and branch correlation
- cleaner replay reconstruction
