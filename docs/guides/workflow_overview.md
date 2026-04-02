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
clawgraph artifact bootstrap --template openclaw-defaults --session latest
clawgraph readiness --session latest --builder preference
```

What is automatic:

- proxy capture
- generated `session_id`, `run_id`, and `request_id`
- session and current-run reuse for cookie-backed browser clients
- replay and inspect views
- E1 annotation bootstrap on the latest captured session

What stays optional:

- stable ids through headers
- semantic events
- custom artifacts

Recommended mental model:

- `session` is the durable container you inspect first
- `run` is one execution episode inside that session
- `slice` is the stable task category you register once
- `cohort` is the frozen set of runs you export from repeatedly
- inspect and replay stay session-oriented by default
- repeated export should become cohort-oriented once you move beyond a single run

## 2. Semi-automatic pipeline

Best for:

- RL engineers
- evaluation teams
- platform teams gating export

Default path:

```bash
clawgraph list readiness --builder preference
clawgraph slice register --slice-id slice.capture \
  --task-family captured_agent_task \
  --task-type generic_proxy_capture \
  --taxonomy-version clawgraph.bootstrap.v1 \
  --sample-unit branch \
  --verifier-contract clawgraph.request_outcome_ratio.v1 \
  --risk-level medium \
  --default-use training_candidate \
  --owner ml-team
clawgraph slice candidates --slice-id slice.capture --min-quality-confidence 0.6
clawgraph cohort freeze --slice-id slice.capture --name capture-train
clawgraph export dataset --builder preference --cohort-id <cohort-id> --out out/preference.jsonl
```

What is automatic:

- built-in supervision bootstrap
- builder-specific readiness
- explicit candidate-pool resolution from registered slices
- cohort freeze plus manifest
- dataset snapshot export plus manifest
- recent-run scanning for `clawgraph list readiness`

What stays manual:

- choosing the builder
- choosing slice boundaries and cohort filters
- deciding when to freeze and export

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
