# Workflow Overview

ClawGraph now has three practical workflow shapes.

Use this page when you want to decide how much of the system should stay manual
and how much should be automated.

## 1. Zero-config runtime capture

Best for:

- existing OpenClaw-style runtimes
- fast production onboarding
- teams that want signal before changing runtime code

Default path:

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db

clawgraph inspect session --session latest
clawgraph replay --session latest
clawgraph pipeline run --session latest --builder preference --dry-run
```

What is automatic:

- proxy capture
- generated `session_id`, `run_id`, and `request_id`
- session and current-run reuse for cookie-backed browser clients
- replay and inspect views
- pipeline preview on the latest captured session

What stays optional:

- stable ids through headers
- semantic events
- custom artifacts

Recommended mental model:

- `session` is the durable container you inspect first
- `run` is one execution episode inside that session
- inspect and replay stay session-oriented by default
- readiness, artifact bootstrap, pipeline, and export are run-oriented by default

## 2. Semi-automatic pipeline

Best for:

- RL engineers
- evaluation teams
- platform teams gating export

Default path:

```bash
clawgraph list readiness --builder preference
clawgraph pipeline run --session latest --builder preference --dry-run
clawgraph pipeline run --session latest --builder preference --out out/preference.jsonl
```

What is automatic:

- built-in supervision bootstrap
- builder-specific readiness
- dataset export plus manifest
- latest-run selection inside one session when `--run-id` is omitted
- recent-run scanning for `clawgraph list readiness`

What stays manual:

- choosing the builder
- choosing export scope
- deciding when to persist or export

## 3. Manual control

Best for:

- evaluator reruns
- hand-authored artifacts
- research workflows that need exact control

Typical path:

```bash
clawgraph replay --session latest
clawgraph artifact bootstrap --template request-outcome-scores --session latest --dry-run
clawgraph artifact append --type score --target-ref latest-model-response --producer team.judge --payload '{"score": 1.0}'
clawgraph artifact list --session latest --latest-only
clawgraph readiness --session latest --builder binary_rl
clawgraph export dataset --builder binary_rl --session latest --out out/binary_rl.jsonl
```

This path is slower, but it gives you explicit control over every supervision
step.

## Recommended default

For most teams, the recommended order is:

1. Start with zero-config runtime capture.
2. Move to the semi-automatic pipeline for repeated export.
3. Drop to manual control only when templates or heuristics are not enough.

## Related pages

- [OpenClaw Integration](./openclaw_integration.md)
- [15-Minute Path](./fifteen_minute_path.md)
- [User Stories](./user_stories.md)
- [Dataset Builders](./dataset_builders.md)
