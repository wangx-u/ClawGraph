# Proxy Mode

Proxy mode is the default adoption path for ClawGraph.

Use it when you want capture first and runtime changes later.

## Smallest working path

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

Then point model and tool traffic at the proxy and send one real request.

Inspect the result with:

```bash
clawgraph inspect session --session latest
clawgraph list runs --session latest
clawgraph replay --session latest
clawgraph pipeline run --session latest --builder preference --dry-run
```

What it gives you:

- low-intrusion capture
- request and user ids
- timing-oriented inspect views
- replay-ready facts
- branch inference v1
- readiness checks
- dataset export capability
- streaming chunk capture for chat-completions
- sticky session and run identity for cookie-backed browser clients

What it does not guarantee:

- planner boundaries
- explicit retry reasons
- controller decisions
- stop versus continue semantics
- full subagent structure unless the runtime routes that activity through the proxy surfaces or emits hints

## Add more structure only when needed

- add stable headers when replay grouping across clients is weak
- rotate the run without changing the session with `x-clawgraph-new-run: 1` or `client.start_new_run()`
- add semantic events only for retry, fallback, routing, or branch-open decisions that matter for export fidelity

## Best next pages

- [OpenClaw Integration](./openclaw_integration.md) for rollout choices
- [Replay and Debug](./replay_and_debug.md) for inspection workflow
- [`examples/openclaw_proxy_minimal`](../../examples/openclaw_proxy_minimal/README.md) for a runnable repository example
