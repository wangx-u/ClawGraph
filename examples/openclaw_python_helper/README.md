# OpenClaw Python Helper

Use this example when you want the lowest-friction Python integration.

Best for:

- OpenAI-compatible Python runtimes
- teams that want proxy capture without wiring headers manually
- adding semantic events from the same runtime context

## What this uses

- [`ClawGraphRuntimeClient`](../../src/clawgraph/runtime/client.py)
- `clawgraph proxy`

## Minimal example

```python
from clawgraph import ClawGraphRuntimeClient

client = ClawGraphRuntimeClient(base_url="http://127.0.0.1:8080")

response = client.chat_completions(
    {"messages": [{"role": "user", "content": "compare ART and AReaL"}]}
)

tool_response = client.tool(
    "/tools/run",
    {"tool": "web_search", "arguments": {"q": "agent rl"}},
)

client.emit_semantic(
    kind="retry_declared",
    payload={
        "branch_id": "br_retry_1",
        "branch_type": "retry",
        "status": "succeeded",
    },
)
```

Or run the repository example directly:

```bash
PYTHONPATH=src python examples/openclaw_python_helper/runtime_helper_minimal.py \
  --base-url http://127.0.0.1:8080
```

## What you get automatically

- proxy-assigned `session_id`, `run_id`, and `request_id`
- cookie-based session reuse across requests
- one session context reused for model calls, tool calls, and semantic events

## Recommended next step

After sending a few requests, inspect the latest session:

```bash
clawgraph inspect session --session latest
clawgraph replay --session latest
clawgraph pipeline run --session latest --builder preference --dry-run
```

If you later need stronger replay grouping across workers or services, add
stable ids explicitly through `ClawGraphSession`.
