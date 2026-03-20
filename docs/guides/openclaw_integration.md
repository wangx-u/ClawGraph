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

Typical endpoints:

- `/v1/chat/completions`
- `/v1/responses`
- `/tools/*`

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
2. Move to proxy mode for real runtime traffic.
3. Add stable run, request, and user ids.
4. Add semantic events only for retry, fallback, and routing decisions.
5. Use `clawgraph artifact bootstrap --template openclaw-defaults --session latest --dry-run` before hand-authored artifacts.
6. Prefer declared branches over inferred branches for training-critical flows.

Next:

- follow [15-Minute Path](./fifteen_minute_path.md) if you want the full capture-to-export flow
- use [Quickstart](./quickstart.md) for a full local first run
- use [Examples](./examples.md) to choose a repository example by integration depth
- use [Semantic Mode](./semantic_mode.md) when inferred branches stop being enough
