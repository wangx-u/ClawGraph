# OpenClaw Integration

ClawGraph is designed to be OpenClaw-first.

## Mode A: Transparent Proxy

Change only model and tool endpoints.

Best for:

- quick onboarding
- demos
- early capture
- streaming chat-completions passthrough

Typical endpoints:

- `/v1/chat/completions`
- `/tools/*`

## Mode B: Proxy plus Context Headers

Add stable metadata such as:

- `x-clawgraph-session-id`
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

1. Start with proxy mode only.
2. Add stable request and user ids.
3. Add semantic events only for retry, fallback, and routing decisions.
4. Prefer declared branches over inferred branches for training-critical flows.
