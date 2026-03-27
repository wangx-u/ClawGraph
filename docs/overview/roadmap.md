# Roadmap

This page summarizes implementation status for the main ClawGraph architecture
layers.

Status values:

- `Implemented`: usable in the current product surface
- `Partial`: present, but not yet complete enough to match the design goal
- `Planned`: not yet implemented

## Status summary

| Area | Status | Current state |
| --- | --- | --- |
| Core substrate | `Implemented` | Proxy capture, immutable facts, run/session scope model, replay/inspect, artifact append, built-in builders |
| Branch-aware learning workflows | `Partial` | Retry/fallback/subagent basics exist, but branch fidelity and overlay workflows are incomplete |
| Semantic fidelity expansion | `Partial` | Semantic ingress exists, but process-level semantics are still minimal |
| Builder ecosystem | `Partial` | Registry exists, but OPD/process builders and selection APIs are still missing |
| Production hardening | `Planned` | Performance, snapshotting, and non-SQLite scale paths still need work |

## Phase breakdown

### Phase 1: Core substrate

Status: `Implemented`

Delivered:

- proxy-first capture for model and tool traffic
- immutable fact log with SQLite storage
- `session -> run -> request -> branch` scope model
- replay, inspect, readiness, artifact, and export CLI flows
- built-in `sft`, `preference`, and `binary_rl` builders

Next gaps:

- stable programmatic query APIs
- incremental or materialized run views
- stronger public contracts for integrations outside the CLI

### Phase 2: Branch-aware learning workflows

Status: `Partial`

Delivered:

- basic retry, fallback, and hinted subagent branch handling
- branch comparison for preference export
- branch-oriented artifact bootstrap templates

Next gaps:

- stable `repair` and `explore` branch types
- replay with artifact overlays and branch-decision audit views
- richer artifact workflows such as critique, constraint, and distillation
  targets
- stronger subagent capture that does not rely mainly on hints

### Phase 3: Semantic fidelity expansion

Status: `Partial`

Delivered:

- semantic ingress endpoint and runtime helpers
- declared retry and fallback events
- declared branch open and close events

Next gaps:

- planner and controller semantics
- stop, continue, uncertainty, and interruption semantics
- step-level process semantics consumable by builders

### Phase 4: Builder ecosystem

Status: `Partial`

Delivered:

- builder registry with alias support
- external builder loading through Python modules or entry points
- readiness and export resolved through the registry

Next gaps:

- OPD builder
- process RM builder
- branch comparison builders beyond the current preference path
- selection/query APIs and memory overlays
- official example builders and SDK-quality tests

### Cross-cutting production hardening

Status: `Planned`

Needed:

- shared correlation caches or materialized views
- better pagination and filtering APIs
- export snapshot and version contracts
- stronger store abstractions and batch flows

Full repository roadmap:

- [ROADMAP.md](../../ROADMAP.md)
