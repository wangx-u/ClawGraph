---
layout: home

hero:
  name: ClawGraph
  text: Immutable, branch-aware execution graphs for OpenClaw-style agents
  tagline: Proxy-first capture for real agent execution. Replay, judge, rank, and export datasets for async RL and distillation from the same source of truth.
  image:
    src: /clawgraph-logo.png
    alt: ClawGraph logo
  actions:
    - theme: brand
      text: Validate Locally
      link: /guides/quickstart
    - theme: alt
      text: Connect Runtime
      link: /guides/openclaw_integration
    - theme: alt
      text: 中文入门
      link: /zh-CN/README

features:
  - title: Built for learning, not dashboards
    details: ClawGraph is optimized for replay, judgment, ranking, dataset construction, and training reuse.
  - title: Proxy-first adoption
    details: Route runtime traffic through ClawGraph first. Add richer semantics later only when needed.
  - title: Inspect before you export
    details: Session, request, branch, artifact, and readiness views make training decisions auditable.
  - title: Branch-aware execution graphs
    details: Retries, fallbacks, repairs, and subagents are first-class rather than hidden in flat logs.
  - title: Typed supervision artifacts
    details: Scores, labels, rankings, critiques, constraints, and distillation targets live outside immutable facts.
  - title: User-defined dataset builders
    details: Turn the same execution graph into SFT, preference, binary RL, OPD, or custom datasets.
  - title: Downstream-ready
    details: Export replay and datasets into async RL, distillation, and evaluation stacks without reinstrumenting the runtime.
---

> Most tracing systems are built for monitoring. ClawGraph is built for learning.

ClawGraph helps teams move from flat logs and one-off debugging toward
reproducible learning workflows:

- capture real agent traffic once
- inspect what happened before training
- attach supervision without mutating history
- export training data only when a run is ready

## Start with one job

Choose the next action you need, not the whole system.

### 1. Validate one local run

Use this if you want the fastest proof that ClawGraph works on your machine.

- Read [`Quickstart`](/guides/quickstart)
- Prefer one longer guided path? Use [`15-Minute Path`](/guides/fifteen_minute_path)
- Prefer runnable repo files? Open [`examples/openclaw_quickstart`](../examples/openclaw_quickstart/README.md)

### 2. Connect a real runtime

Use this if you already run an OpenClaw-style or OpenAI-compatible stack.

- Read [`OpenClaw Integration`](/guides/openclaw_integration)
- Keep capture low-friction with [`Proxy Mode`](/guides/proxy_mode)
- Need runnable examples? Start with [`examples/openclaw_proxy_minimal`](../examples/openclaw_proxy_minimal/README.md)

### 3. Export training data

Use this if you already have captured runs and need files for SFT, preference,
or RL workflows.

- Read [`Dataset Builders`](/guides/dataset_builders)
- Use [`Export to Async RL`](/guides/export_to_async_rl) for the handoff boundary
- Prefer runnable repo files? Open [`examples/export_to_async_rl`](../examples/export_to_async_rl/README.md)

If you want a gentler decision page before committing to one path, use
[`Start Here`](/guides/start_here). Prefer Chinese onboarding? Start with
[`中文入门文档`](/zh-CN/README).

## Use these after the first run

- [`Replay and Debug`](/guides/replay_and_debug) when you need to answer what happened before training
- [`Workflow Overview`](/guides/workflow_overview) when deciding how much should stay manual
- [`User Stories`](/guides/user_stories) when mapping ClawGraph to runtime, RL, evaluation, or platform work
- [`Examples`](/guides/examples) when you prefer runnable artifacts over prose

## Reference

- [`CLI Reference`](/reference/cli_reference) for command flags and target shortcuts
- [`Execution Facts`](/concepts/execution_facts) and [`Artifact Protocol`](/concepts/artifact_protocol) for the data model
- [`Design Overview`](/design/index) for proxy-to-RL dataset curation, task-model mapping, and small-model replacement standards
- [`What is ClawGraph`](/overview/what_is_clawgraph), [`Architecture`](/overview/architecture), [`Roadmap`](/overview/roadmap), and [`Why Not Tracing`](/overview/why_not_tracing) for system design
