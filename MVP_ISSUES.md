# v0.1 MVP Issue Backlog

This document tracks the initial work required to make ClawGraph real.

## Theme 1: Protocol and schemas

- [ ] Define `event.schema.json` v1
- [ ] Define `branch.schema.json` v1
- [ ] Define `artifact.schema.json` v1
- [ ] Define `semantic_event.schema.json` v1
- [ ] Add versioning and compatibility policy

## Theme 2: Proxy capture

- [ ] Implement OpenAI-compatible chat-completions proxy stub
- [ ] Implement tool proxy stub
- [ ] Capture streaming chunks and timing metadata
- [ ] Persist captured facts to sqlite
- [ ] Support context headers for session and parent correlation

## Theme 3: Fact log and views

- [ ] Add append-only fact store interface
- [ ] Add session view builder
- [ ] Add episode view builder
- [ ] Add branch inference v1
- [ ] Add replay timeline renderer

## Theme 4: Artifacts

- [ ] Add artifact append API
- [ ] Support `score`, `ranking`, `critique`, and `target` artifact families
- [ ] Add target references for run, session, branch, and fact
- [ ] Add artifact lineage fields

## Theme 5: Dataset builders

- [ ] Add builder interface
- [ ] Implement SFT builder
- [ ] Implement preference builder
- [ ] Implement binary RL builder
- [ ] Add dataset export manifests and checksums

## Theme 6: CLI and UX

- [ ] Add `clawgraph proxy`
- [ ] Add `clawgraph replay`
- [ ] Add `clawgraph export dataset`
- [ ] Add fixture-backed CLI tests
- [ ] Add example-driven quickstart

## Theme 7: Docs and examples

- [ ] Publish docs site skeleton
- [ ] Add OpenClaw transparent proxy example
- [ ] Add headers integration example
- [ ] Add semantic contract example
- [ ] Add async RL export example

## Exit criteria

ClawGraph v0.1 is done when a user can:

1. run a runtime through the proxy
2. persist immutable facts locally
3. inspect a replay timeline
4. attach supervision artifacts
5. export at least one SFT dataset and one preference dataset
