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
      text: Start Here
      link: /guides/start_here
    - theme: alt
      text: Quickstart
      link: /guides/quickstart
    - theme: alt
      text: Read Architecture
      link: /overview/architecture

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
- export training data only when a session is ready

## New here?

Start with the shortest useful path:

1. Run [`15-Minute Path`](/guides/fifteen_minute_path) if you want one guided
   flow from local validation to export.
2. Run [`Quickstart`](/guides/quickstart) if you only want the shortest first
   success path.
3. Read [`OpenClaw Integration`](/guides/openclaw_integration) before wiring a
   real runtime.

## Choose your path

- **I need a first successful run**
  Start with [`Start Here`](/guides/start_here).
- **I want one guided path from first run to export**
  Start with [`15-Minute Path`](/guides/fifteen_minute_path).
- **I run an OpenClaw-style runtime**
  Start with [`OpenClaw Integration`](/guides/openclaw_integration).
- **I need better debugging before training**
  Start with [`Replay and Debug`](/guides/replay_and_debug).
- **I need datasets for training**
  Start with [`Dataset Builders`](/guides/dataset_builders) and
  [`Export to Async RL`](/guides/export_to_async_rl).
- **I want the protocol and data model**
  Start with [`Execution Facts`](/concepts/execution_facts) and
  [`Artifact Protocol`](/concepts/artifact_protocol).

## Common workflows

### Local first run

- [`Quickstart`](/guides/quickstart)
- [`User Stories`](/guides/user_stories)

### Connect a production runtime

- [`OpenClaw Integration`](/guides/openclaw_integration)
- [`Proxy Mode`](/guides/proxy_mode)
- [`Semantic Mode`](/guides/semantic_mode)

### Export to training systems

- [`Dataset Builders`](/guides/dataset_builders)
- [`Export to Async RL`](/guides/export_to_async_rl)
- [`CLI Reference`](/reference/cli_reference)

## Docs map

- **Start here**
  [`Start Here`](/guides/start_here), [`Quickstart`](/guides/quickstart)
- **Run one guided flow**
  [`15-Minute Path`](/guides/fifteen_minute_path)
- **Browse examples**
  [`Examples`](/guides/examples)
- **Learn the model**
  [`What is ClawGraph`](/overview/what_is_clawgraph),
  [`Architecture`](/overview/architecture),
  [`Why Not Tracing`](/overview/why_not_tracing)
- **Work with real runs**
  [`Replay and Debug`](/guides/replay_and_debug),
  [`User Stories`](/guides/user_stories)
- **Build and export supervision**
  [`Dataset Builders`](/guides/dataset_builders),
  [`Custom Artifacts and Builders`](/guides/custom_artifacts_and_builders)

## Good next pages

- If you want one guided path, read [`15-Minute Path`](/guides/fifteen_minute_path).
- If you want the fastest local validation, read [`Quickstart`](/guides/quickstart).
- If you already have a runtime, read [`OpenClaw Integration`](/guides/openclaw_integration).
- If you need training outputs, read [`Dataset Builders`](/guides/dataset_builders).
