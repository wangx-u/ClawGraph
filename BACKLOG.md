# Backlog

This document tracks the next production milestones for ClawGraph.

## Foundation already in repo

- versioned protocol schemas
- proxy capture for OpenAI-compatible model endpoints and tool endpoints
- immutable sqlite fact log
- session, request, branch, and replay views
- typed supervision artifacts with status and supersession
- SFT, preference, and binary RL dataset exports
- quickstart-backed CLI coverage

## Next milestones

### 1. Storage and scale

- add Postgres and object-storage backends
- support large payload offloading with content-addressed blobs
- add retention and compaction policies for local development stores

### 2. Runtime fidelity

- expand semantic contract coverage for routing and subagent events
- improve branch inference for multi-controller and sibling-branch flows
- add richer request classification across OpenAI-compatible endpoints

### 3. Supervision and builders

- add branch comparison and OPD builders
- add process-reward and critique dataset builders
- add richer built-in artifact templates for tool validity and routing quality

### 4. Operational surface

- add machine-readable inspect and replay outputs for automation
- add export manifests with stronger provenance filters and checksums
- add compatibility tests across supported upstream API shapes

## Acceptance bar

Each milestone should preserve four guarantees:

1. facts remain immutable
2. derived views stay reproducible
3. artifacts remain externally versioned
4. export behavior stays auditable and test-covered
