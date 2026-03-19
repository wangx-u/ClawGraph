# Architecture

ClawGraph follows a strict layered architecture:

```text
OpenClaw / agent runtime
    -> Proxy Capture Layer
    -> Immutable Fact Log
    -> Graph / Replay Views
    -> Artifact Engine
    -> Dataset Builders
    -> Async RL / Distill Bridges
```

## Layer responsibilities

### Proxy Capture Layer

Intercepts model, tool, and subagent traffic with low integration friction.

### Immutable Fact Log

Stores append-only source facts. This is the only source of truth.

### Graph / Replay Views

Derives reusable views such as sessions, episodes, branches, and replay
timelines.

### Artifact Engine

Attaches supervision externally as versioned artifacts such as scores,
rankings, critiques, constraints, and teacher targets.

### Dataset Builders

Transforms graphs and artifacts into training-ready datasets.

### Async RL / Distill Bridges

Exports datasets and lineage into downstream training systems.
