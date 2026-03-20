# OpenClaw Proxy Minimal

Use this when you want the smallest possible integration with a real runtime.

## What changes in the runtime

- point model traffic at `clawgraph proxy`
- point tool traffic at `clawgraph proxy`

## What you get

- immutable facts for model and tool calls
- session and request inspection
- replay for captured runs
- a clean path to artifact bootstrap and dataset export

## Best next step

If sessions are hard to correlate, move to
[`../openclaw_with_headers`](../openclaw_with_headers/README.md).

This example covers the lowest-friction integration:

- route model traffic through ClawGraph
- route tool traffic through ClawGraph
- capture immutable facts
- inspect replay
