# ClawGraph

### Immutable, branch-aware execution graphs for OpenClaw-style agents

Capture real agent execution with proxy-first adoption and optional semantic
runtime signals. Replay, judge, rank, and export reusable datasets for async
RL and distillation from the same source of truth.

> Most tracing systems are built for monitoring. ClawGraph is built for
> learning.

## What is ClawGraph?

ClawGraph is a learning-native execution substrate for OpenClaw-style agents.

It sits between:

- runtime execution
- evaluation, supervision, dataset building, and training systems

ClawGraph captures immutable execution facts from real agent runs, derives
branch-aware execution graphs, attaches typed supervision artifacts, and
exports datasets without requiring the runtime to be rewritten.

## What ClawGraph is not

ClawGraph is not:

- a new agent runtime
- a trainer
- a fixed reward system
- a dashboard-first observability product
- tied to a single RL, SFT, DPO, or distillation recipe

## Core promise

Capture once. Reuse everywhere.

The same agent run should support:

- replay
- failure analysis
- ranking
- evaluation
- dataset construction
- async RL
- distillation

## Architecture

```text
OpenClaw / Claw-style Agent Runtime
(model, tools, subagents, user I/O)
                    |
                    v
          1. Proxy Capture Layer
   model proxy · tool proxy · subagent proxy
                    |
                    v
          2. Immutable Fact Log
     append-only execution facts
                    |
        +-----------+------------+
        |                        |
        v                        v
  3a. Semantic Contract    3b. Graph / View Builders
  (optional runtime         session / episode /
   semantics)               branch / replay / graph
        +-----------+------------+
                    |
                    v
             4. Artifact Engine
      scores · critiques · rankings · targets
                    |
                    v
             5. Dataset Builders
      SFT · preference · binary RL · OPD · RM
                    |
                    v
         6. Async RL / Distill Bridges
```

## Design principles

1. Facts are immutable.
2. Graphs are derived.
3. Artifacts are external.
4. Branching is first-class.
5. Proxy-first, semantics-later.
6. Supervision is typed.
7. Training is downstream.
8. Every export is reproducible.

## Why this exists

Most agent teams still face the same problems:

- execution history lives in logs, not reusable structured facts
- retries, fallbacks, repairs, and subagents are hard to reconstruct
- replay, evaluation, and dataset generation are separate ad hoc pipelines
- learning logic changes quickly, but historical traces are not reusable
- agent teams want learning from real runs without rewriting the runtime

ClawGraph fixes this with a simple rule:

1. capture execution facts once
2. never mutate those facts
3. derive graphs and replay views from them
4. attach supervision externally
5. export datasets through versioned builders

## Adoption model

ClawGraph intentionally separates adoption from semantic fidelity.

### Proxy-first

Start by routing model and tool traffic through the proxy.

This gives you:

- immediate capture
- minimal runtime changes
- replay readiness
- export readiness

### Semantics later

When you need richer learning fidelity, add semantic events such as:

- plan created
- subgoal selected
- retry declared
- fallback declared
- controller route decided
- stop reason

Proxy solves adoption. Semantic contract solves semantic fidelity.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
clawgraph --help
```

Start the proxy:

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

Inspect replay:

```bash
clawgraph replay --session latest
```

Export a dataset:

```bash
clawgraph export dataset --builder preference \
  --session latest \
  --out ./exports/preference.jsonl
```

## Strongest ideas

### 1. Immutable execution facts

Facts remain reusable even when prompts, judges, ranking logic, reward
formulas, and builders evolve.

### 2. Branch-aware execution graphs

Agent learning needs more than a flat message list. ClawGraph models retries,
fallbacks, repairs, subagents, and sibling branch comparisons directly.

### 3. Typed supervision artifacts

ClawGraph models supervision as versioned external artifacts rather than a
single reward scalar. The same run can power SFT, preference learning, binary
RL, OPD, process reward modeling, and offline evaluation.

## Repository layout

```text
clawgraph/
├── README.md
├── docs/
├── examples/
├── schemas/
├── src/clawgraph/
├── tests/
├── benchmarks/
└── rfc/
```

## Start here

- [Roadmap](ROADMAP.md)
- [MVP issues](MVP_ISSUES.md)
- [Examples](examples/README.md)
- [Schemas](schemas/README.md)
- [Contributing](CONTRIBUTING.md)
- [OpenClaw Integration](docs/openclaw_integration.md)
- [Event Protocol](docs/event_protocol.md)
- [Artifact Protocol](docs/artifact_protocol.md)
- [Branching Model](docs/branching.md)
- [Semantic Contract](docs/semantic_contract.md)
- [Supervision Model](docs/supervision.md)
- [Dataset Builders](docs/dataset_builders.md)
- [FAQ](docs/faq.md)
- [Roadmap](docs/roadmap.md)

## Current focus

The initial ClawGraph release focuses on:

- proxy-first capture
- immutable fact protocol
- session / episode / branch / replay views
- typed artifact protocol
- sample builders
- export bridges to downstream systems
