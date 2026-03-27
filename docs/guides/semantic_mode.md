# Semantic Mode

Semantic mode builds on proxy mode.

Use it when inferred branches are no longer good enough for replay, judgment, or
training export.

Use it when you want:

- explicit branch and routing semantics
- better replay fidelity
- future process supervision inputs
- more accurate branch interpretation
- higher-quality sample building

Typical semantic signals:

- `plan_created`
- `subgoal_selected`
- `retry_declared`
- `branch_open_declared`
- `fallback_declared`
- `controller_route_decided`

## Add semantics in this order

1. capture real traffic through proxy mode first
2. inspect where inferred branches diverge from what the runtime actually did
3. emit semantic events only for those high-value decisions
4. compare replay, readiness, and export quality again

Signals worth adding first:

- `retry_declared`
- `fallback_declared`
- `controller_route_decided`
- `branch_open_declared`

Current boundary:

- built-in builders already benefit from clearer branch semantics
- planner and process-specific builders are not yet built in
- semantic facts still matter now because they keep future supervision on the immutable-fact side of the boundary

## Best next pages

- [OpenClaw Integration](./openclaw_integration.md) for the rollout model
- [Replay and Debug](./replay_and_debug.md) when you need to compare inferred versus declared structure
- [`examples/openclaw_with_semantic_contract`](../../examples/openclaw_with_semantic_contract/README.md) for a runnable repository example
