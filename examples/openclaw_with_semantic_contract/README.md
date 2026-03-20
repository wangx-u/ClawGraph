# OpenClaw With Semantic Contract

Use this when inferred branches are not enough for training-critical flows.

## Emit explicit runtime signals for

- `retry_declared`
- `fallback_declared`
- `branch_open_declared`
- `branch_close_declared`
- `controller_route_decided`

## What you get

- declared branch lineage
- better branch comparison quality
- cleaner preference and binary RL exports
- less ambiguity in replay and debugging

## Best next step

After semantic events are flowing, run artifact bootstrap and export builders
for the sessions you care about.

This example covers:

- proxy capture
- runtime-declared semantic events
- higher-fidelity branch reconstruction
- richer dataset exports
