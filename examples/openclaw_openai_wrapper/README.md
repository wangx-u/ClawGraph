# OpenClaw OpenAI Wrapper

Use this example when you already have code built around the OpenAI Python SDK
shape and want the smallest possible change set.

Best for:

- existing `client.chat.completions.create(...)` code
- existing `client.responses.create(...)` code
- teams that want ClawGraph headers injected without switching to raw HTTP

## What this uses

- [`ClawGraphOpenAIClient`](../../src/clawgraph/runtime/openai.py)
- an existing OpenAI-compatible Python client

## Minimal example

```python
from openai import OpenAI

from clawgraph import ClawGraphOpenAIClient

base_client = OpenAI(
    base_url="http://127.0.0.1:8080",
    api_key="unused-for-local-proxy",
)
client = ClawGraphOpenAIClient(base_client)

response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "compare ART and AReaL"}],
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

## What you get automatically

- generated or reused `session_id` and `run_id`
- a fresh `request_id` per SDK call
- merged `extra_headers` without changing your call sites much
- semantic event posting through the same ClawGraph session context

## Recommended next step

- If you do not need the OpenAI SDK shape, use
  [`../openclaw_python_helper`](../openclaw_python_helper/README.md).
- After a few calls, inspect the captured session:

```bash
clawgraph inspect session --session latest
clawgraph replay --session latest
clawgraph pipeline run --session latest --builder preference --dry-run
```
