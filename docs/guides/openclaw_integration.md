# OpenClaw Integration

ClawGraph is designed to be OpenClaw-first.

This guide is Step 2 of the [15-Minute Path](./fifteen_minute_path.md).

Start with the lowest-friction mode that gives you useful signal, then add
more structure only where learning fidelity requires it.

## Mode A: Transparent Proxy

Change only model and tool endpoints.

Best for:

- quick onboarding
- initial rollout
- production capture
- streaming chat-completions passthrough
- zero-config first run

Typical endpoints:

- `/v1/chat/completions`
- `/v1/responses`
- `/tools/*`

What ClawGraph now does automatically in this mode:

- generates `session_id`, `run_id`, and `request_id` when they are missing
- returns them in response headers
- sets session and run cookies so browser-style clients can keep the same session and current run without runtime changes
- creates a fresh run automatically only when the client is stateless or does not replay the run cookie
- forwards upstream cookies except the internal ClawGraph identity cookies

For Python runtimes, you can also use the built-in helper instead of wiring
headers yourself:

```python
from clawgraph import ClawGraphRuntimeClient

client = ClawGraphRuntimeClient(base_url="http://127.0.0.1:8080")

response = client.chat_completions(
    {"messages": [{"role": "user", "content": "compare ART and AReaL"}]}
)

client.emit_semantic(
    kind="retry_declared",
    payload={"branch_type": "retry", "status": "succeeded"},
    branch_id="br_retry_1",
)
```

`emit_semantic()` binds to the most recent request in the current run when you
do not pass an explicit target request id, so the default path stays low-friction.
If you want a new run boundary without rotating the session, call
`client.start_new_run()`.

For browser or gateway clients that are only using proxy mode, send
`x-clawgraph-new-run: 1` on the next proxied request to rotate the run while
keeping the same session.

If you want a runnable repository example, start with
[`examples/openclaw_proxy_minimal`](../../examples/openclaw_proxy_minimal/README.md).
Move to [`examples/openclaw_python_helper`](../../examples/openclaw_python_helper/README.md)
when you want helper-managed requests and semantic ingress.

If you already use the OpenAI Python SDK shape, use
[`examples/openclaw_openai_wrapper`](../../examples/openclaw_openai_wrapper/README.md)
for a wrapper that injects ClawGraph headers through `extra_headers`.

## Mode B: Proxy plus Context Headers

Add stable metadata such as:

- `x-clawgraph-session-id`
- `x-clawgraph-run-id`
- `x-clawgraph-thread-id`
- `x-clawgraph-task-id`
- `x-clawgraph-user-id`
- `x-clawgraph-parent-id`

Best for:

- cleaner graph reconstruction
- better branch grouping

This is the lowest-friction way to improve:

- request-level inspection
- user/session debugging
- replay fidelity
- downstream sample selection

## Mode C: Proxy plus Semantic Contract

Emit explicit runtime semantics where learning fidelity matters.

Current semantic ingress path:

- `POST /v1/semantic-events`

Typical events:

- `retry_declared`
- `fallback_declared`
- `branch_open_declared`
- `branch_close_declared`
- `controller_route_decided`

Recommended rollout:

1. Start with `clawgraph bootstrap openclaw` if you need a first-run local baseline.
2. Move to proxy mode for real runtime traffic and let ClawGraph auto-assign ids first.
3. Inspect the session first, then pick a run with `clawgraph list runs --session latest` when you need run-specific export.
4. Add stable run, request, and user ids only when you need stronger replay grouping across clients.
5. Add semantic events only for retry, fallback, and routing decisions.
6. Use `clawgraph pipeline run --session latest --builder preference --dry-run` before hand-authored artifacts.
7. Prefer declared branches over inferred branches for training-critical flows.

Next:

- follow [15-Minute Path](./fifteen_minute_path.md) if you want the full capture-to-export flow
- use [Quickstart](./quickstart.md) for a full local first run
- use [Examples](./examples.md) to choose a repository example by integration depth
- use [Semantic Mode](./semantic_mode.md) when inferred branches stop being enough
