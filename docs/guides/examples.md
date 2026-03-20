# Examples

Use this page to choose the example that matches your integration depth.

## Recommended order

1. `examples/openclaw_quickstart`
2. `examples/openclaw_proxy_minimal`
3. `examples/openclaw_python_helper`
4. `examples/openclaw_openai_wrapper`
5. `examples/openclaw_with_headers`
6. `examples/openclaw_with_semantic_contract`
7. `examples/export_to_async_rl`

## Example catalog

### `examples/openclaw_quickstart`

Best for:

- a full first run
- local validation before connecting a real runtime

What you get:

- one captured session
- one declared retry branch
- artifacts, readiness, and export flow

### `examples/openclaw_proxy_minimal`

Best for:

- the lowest-friction OpenClaw integration
- teams that want capture first and semantics later

What you get:

- proxy-first traffic capture
- replay and inspection for real runs

### `examples/openclaw_python_helper`

Best for:

- Python runtimes that want fewer manual headers
- teams that want one helper for model calls, tool calls, and semantic events

What you get:

- helper-driven session reuse
- proxy-assigned identity carried automatically
- lower-friction semantic ingress

### `examples/openclaw_openai_wrapper`

Best for:

- existing OpenAI SDK call sites
- teams that want `extra_headers` injected automatically

What you get:

- wrapper-based header injection
- stable ClawGraph session reuse in existing SDK-shaped code
- optional semantic posting from the same wrapper

### `examples/openclaw_with_headers`

Best for:

- stable session and request correlation
- cleaner run and user scoping

What you get:

- better request inspection
- better branch grouping
- cleaner readiness and export selection

### `examples/openclaw_with_semantic_contract`

Best for:

- higher-fidelity retry and fallback modeling
- training-critical flows where inferred branches are not enough

What you get:

- declared branch lineage
- cleaner branch comparison and supervision

### `examples/export_to_async_rl`

Best for:

- teams already capturing sessions
- downstream training handoff

What you get:

- builder-specific JSONL exports
- lineage-aware manifests

## Where to open the files in the repository

All example READMEs live under the repository `examples/` directory. Start with
`examples/README.md` when browsing the source tree.
