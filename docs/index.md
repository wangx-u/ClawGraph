---
layout: home

hero:
  name: ClawGraph
  text: Immutable, branch-aware execution graphs for OpenClaw-style agents
  tagline: Proxy-first capture for real agent execution. Replay, judge, rank, and export datasets for async RL and distillation from the same source of truth.
  actions:
    - theme: brand
      text: Get Started
      link: /guides/quickstart
    - theme: alt
      text: Read Architecture
      link: /overview/architecture
    - theme: alt
      text: View Protocols
      link: /reference/event_protocol

features:
  - title: Built for learning, not dashboards
    details: ClawGraph is optimized for replay, judgment, ranking, dataset construction, and training reuse.
  - title: Proxy-first adoption
    details: Route runtime traffic through ClawGraph first. Add richer semantics later only when needed.
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
