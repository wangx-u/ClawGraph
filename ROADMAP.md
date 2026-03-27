# Roadmap

This roadmap tracks implementation status against ClawGraph's top-level
architecture.

Status values:

- `Implemented`: usable in the current product surface
- `Partial`: present, but not yet complete enough to match the design goal
- `Planned`: not yet implemented

## Current status summary

| Area | Status | Notes |
| --- | --- | --- |
| Core substrate | Implemented | Proxy capture, immutable facts, run/session scope model, replay/inspect, artifact append, built-in export builders |
| Branch-aware learning workflows | Partial | Retry/fallback/subagent basics are present, but branch taxonomy and overlay workflows are incomplete |
| Semantic fidelity expansion | Partial | Semantic ingress exists, but process-level semantics are still minimal |
| Builder ecosystem | Partial | Registry exists and custom builders can plug into export/readiness, but OPD/process builders are missing |
| Production hardening | Planned | Current implementation still relies on repeated full-run scans and local SQLite assumptions |

## Phase 1: Core substrate

Status: `Implemented`

Goal:

Prove that real runtime traffic can be turned into stable, reusable execution
graphs.

Implemented now:

- proxy-first capture for model and tool traffic
- immutable fact protocol and append-only SQLite store
- `session -> run -> request -> branch` scope model
- replay, inspect, readiness, artifact, and export CLI flows
- built-in `sft`, `preference`, and `binary_rl` builders
- dataset builder registry for custom builder integration

Still needed:

- a stable programmatic query API beyond the CLI
- incremental or materialized run views to avoid repeated full-scan inference
- clearer public contracts for store, inspect, and export integrations

Exit criteria:

- large runs remain fast enough to inspect and export without repeated
  whole-run recomputation
- non-CLI integrations can consume stable scope/query APIs

## Phase 2: Branch-aware learning workflows

Status: `Partial`

Goal:

Make ClawGraph visibly better than generic tracing for learning workflows.

Implemented now:

- basic branch inference for mainline, retry, fallback, and hinted subagent flows
- comparable branch pairing for preference export
- branch-oriented artifact bootstrap templates
- lineage fields inside exported records

Still needed:

- stable `repair` and `explore` branch types instead of only documenting them
- richer replay with artifact overlays and branch-decision audit views
- richer artifact families such as critique, constraint, and distillation-target
  workflows
- stronger subagent capture that does not depend mainly on hints

Exit criteria:

- branch taxonomy in docs matches what replay and export reliably produce
- replay and inspect can explain why one branch was preferred, scored, or
  rejected

## Phase 3: Semantic fidelity expansion

Status: `Partial`

Goal:

Raise the semantic ceiling beyond proxy-only capture.

Implemented now:

- semantic ingress endpoint and runtime helpers
- declared retry and fallback events
- declared branch open and close events
- basic subagent semantic hints

Still needed:

- planner and controller semantics
- stop, continue, uncertainty, and interruption semantics
- step-level process semantics that builders can consume directly
- clearer semantic contract versioning and compatibility rules

Exit criteria:

- semantic events are rich enough to support process supervision, not only branch
  hints
- runtime authors can target a small stable semantic contract without guessing

## Phase 4: Builder ecosystem

Status: `Partial`

Goal:

Strengthen ClawGraph as a reusable learning data substrate.

Implemented now:

- builder registry with alias support
- external builder loading via environment modules or Python entry points
- readiness and export paths resolved through the registry

Still needed:

- OPD builder
- process RM builder
- branch comparison builders beyond the current preference path
- selection and query APIs for builder inputs
- memory overlays as a real supported input, not only a conceptual parameter
- official example builders and SDK-quality integration tests

Exit criteria:

- a team can ship one custom builder without editing ClawGraph core code
- OPD and process-style builders are first-party examples, not only roadmap items

## Cross-cutting production hardening

Status: `Planned`

Goal:

Make the substrate durable enough for production capture and repeated export.

Needed work:

- shared correlation caches or materialized views
- better pagination and filtering APIs
- export snapshot/version contracts for downstream training systems
- stronger store abstractions beyond the local SQLite path
- background jobs or batch flows for artifact generation and export

Exit criteria:

- export and readiness no longer depend on repeated ad hoc scans for each run
- downstream trainers can consume versioned snapshots instead of loosely coupled
  ad hoc files
