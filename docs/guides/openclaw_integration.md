# OpenClaw Integration

ClawGraph is designed to be OpenClaw-first.

## Mode A: Transparent Proxy

Change only model and tool endpoints.

Best for:

- quick onboarding
- demos
- early capture

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

## Mode C: Proxy plus Semantic Contract

Emit explicit runtime semantics where learning fidelity matters.
