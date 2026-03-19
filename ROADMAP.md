# Roadmap

This roadmap describes the intended evolution of ClawGraph.

## Phase 1: Core substrate

Focus:

- proxy-first capture
- immutable fact protocol
- local sqlite-backed fact storage
- session, episode, branch, and replay views
- artifact protocol v1
- SFT, preference, and binary RL builders
- replay and export CLI

Goal:

Prove that real runtime traffic can be turned into stable, reusable execution
graphs.

## Phase 2: Branch-aware learning workflows

Focus:

- better branch inference
- replay with artifact overlays
- richer artifact families
- sample lineage
- export improvements for async RL and distillation

Goal:

Make ClawGraph visibly better than generic tracing for learning workflows.

## Phase 3: Semantic fidelity expansion

Focus:

- semantic contract v1
- planner and controller semantics
- retry and fallback declaration
- stop, continue, and uncertainty semantics

Goal:

Raise the semantic ceiling beyond proxy-only capture.

## Phase 4: Builder ecosystem

Focus:

- OPD builder
- process RM builder
- branch comparison builders
- query and selection APIs

Goal:

Strengthen ClawGraph as a reusable learning data substrate.
