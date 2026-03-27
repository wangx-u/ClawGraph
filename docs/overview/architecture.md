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

The boundary is deliberate:

- ClawGraph captures and structures runtime execution.
- ClawGraph does not own model training.
- Facts stay stable even when builders, judges, and reward logic change.

## Layer responsibilities

### Proxy Capture Layer

Intercepts model and tool traffic with low integration friction.
Subagent activity becomes visible when it is routed through those surfaces or
when the runtime emits context or semantic hints.

### Immutable Fact Log

Stores append-only source facts. This is the only source of truth.

### Graph / Replay Views

Derives reusable views such as sessions, runs, branches, and replay
timelines.

## Scope model

ClawGraph uses a small identity model throughout the CLI, replay, and export
layers:

- `session`: durable container for related user or application activity
- `run`: one execution episode inside a session
- `request`: one model, tool, or runtime call inside a run
- `branch`: one alternate path inside a run

In v1, `run` is the concrete episode unit used by builders, readiness checks,
and export commands.

### Artifact Engine

Attaches supervision externally as versioned artifacts such as scores,
rankings, critiques, constraints, and teacher targets.

### Dataset Builders

Transforms graphs and artifacts into training-ready datasets.

### Async RL / Distill Bridges

Exports datasets and lineage into downstream training systems.
