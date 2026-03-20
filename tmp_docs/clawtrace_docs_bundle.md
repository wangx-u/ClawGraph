# ClawGraph Documentation Bundle

下面内容可直接拆分为仓库根目录与 `docs/` 下的完整文档。

---

# README.md

```md
# ClawGraph

### Immutable, branch-aware execution graphs for OpenClaw-style agents

Capture real agent execution with proxy-first adoption and optional semantic runtime signals. Replay, judge, rank, and build datasets from the same source of truth.

> **Most tracing systems are built for monitoring. ClawGraph is built for learning.**

## What is ClawGraph?

ClawGraph is a learning-native execution fact graph substrate for OpenClaw-style agents.

It captures immutable execution facts from real agent runs, organizes them into branch-aware execution graphs, attaches typed supervision artifacts, and lets users export replay, evaluation, ranking, and training datasets without re-instrumenting the runtime.

ClawGraph is designed for the layer between:

- **runtime execution** on one side
- **evaluation, supervision, dataset building, and training systems** on the other

## What ClawGraph is not

ClawGraph is **not**:

- not a new agent runtime
- not a trainer
- not a fixed reward system
- not a dashboard-first observability product
- not tied to a single RL, SFT, DPO, or distillation recipe

## What ClawGraph does

ClawGraph provides:

- **proxy-first capture** for model, tool, and subagent traffic
- an **immutable execution fact log**
- **branch-aware execution graph views** for retries, fallbacks, repairs, and subagents
- **typed supervision artifacts** for scores, labels, rankings, critiques, constraints, and distillation targets
- **sample builders** for user-defined learning pipelines
- **export bridges** for replay, datasets, and downstream systems such as Echo

## Why it exists

Most agent systems today suffer from one or more of these problems:

- execution history lives in raw logs instead of reusable structured facts
- retries, repairs, and branch paths are difficult to reconstruct reliably
- replay, evaluation, and dataset generation use separate ad hoc pipelines
- teams want to learn from real agent runs without rewriting their runtime stack
- reward and judge logic evolves quickly, but historical data becomes polluted or inconsistent

ClawGraph fixes this by enforcing a simple architecture:

1. capture execution facts once
2. never mutate those facts
3. derive graphs and replay views from them
4. attach supervision and sample-building logic externally

## Core principles

1. **Facts are immutable**
2. **Graphs are derived**
3. **Artifacts are external**
4. **Branching is first-class**
5. **Proxy-first, semantics-later**
6. **Supervision is typed**
7. **Training is user-defined**
8. **Capture once, reuse everywhere**

## Learning-native, not dashboard-native

Observability tells you what happened.

ClawGraph gives you reusable execution facts for:

- replay
- judgment
- ranking
- dataset construction
- training

That distinction matters.

Most tracing systems optimize for:

- spans
- dashboards
- alerting
- latency monitoring

ClawGraph optimizes for:

- branch-aware execution structure
- supervision attachment
- dataset lineage
- learning-oriented replay
- reuse across multiple training recipes

## Architecture overview

```text
OpenClaw / Claw-style Agent Runtime
(model · tools · subagents · user I/O)
                    │
                    ▼
          1. Proxy Capture Layer
   model proxy · tool proxy · subagent proxy
                    │
                    ▼
          2. Execution Fact Log
     append-only immutable execution facts
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
3a. Semantic Contract   3b. View Builders
(optional runtime       session / episode /
 semantics)             branch / graph / replay
         └──────────┬──────────┘
                    ▼
          4. Artifact Pipeline
     supervision · memory · analytics · export
                    │
                    ▼
          5. Sample Builders
   SFT · preference · binary RL · OPD · RM
                    │
                    ▼
          6. Downstream Bridges
        Echo · custom trainers · evaluators
```

## Adoption model

ClawGraph intentionally separates **adoption** from **semantic fidelity**.

### Proxy-first

Start by routing your runtime through the ClawGraph proxy.

This gives you:

- immediate execution fact capture
- minimal or zero runtime rewrite
- replay and export readiness
- a common fact layer for future supervision and datasets

### Semantic contract later

When you need higher learning fidelity, add runtime semantics through the optional semantic contract.

This lets your runtime declare richer signals such as:

- plan creation
- controller routing decisions
- retry reasons
- branch-open reasons
- stop decisions
- uncertainty estimates

**Proxy solves adoption. Semantic contract solves semantic fidelity.**

## Quickstart

### 1. Start the proxy

```bash
clawgraph proxy \
  --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

### 2. Point your runtime to the proxy

```yaml
model_endpoint: http://localhost:8080/v1/chat/completions
tool_endpoint: http://localhost:8080/tools
```

### 3. Run the agent normally

No core runtime rewrite is required.

### 4. Inspect replay

```bash
clawgraph replay --session latest
```

### 5. Export a dataset

```bash
clawgraph export dataset \
  --builder preference \
  --session latest \
  --out ./exports/preference.jsonl
```

## The three strongest ideas in ClawGraph

### 1. Immutable execution facts

Historical facts must remain reusable even when:

- prompts change
- judges change
- ranking logic changes
- reward formulas change
- dataset builders evolve

### 2. Branch-aware execution graphs

Agent learning needs more than message lists.

ClawGraph treats the following as first-class:

- retry
- fallback
- repair
- subagent
- sibling branch comparison

### 3. Typed supervision artifacts

ClawGraph models supervision as external typed artifacts, not as one hard-coded reward scalar.

This allows one execution graph to support:

- SFT
- preference learning
- binary RL
- distillation
- process reward modeling
- offline evaluation

## Repository structure

```text
clawgraph/
├── README.md
├── docs/
├── examples/
├── clawgraph/
│   ├── proxy/
│   ├── protocol/
│   ├── store/
│   ├── graph/
│   ├── semantics/
│   ├── artifacts/
│   ├── builders/
│   ├── export/
│   ├── ui/
│   └── cli/
└── tests/
```

## Documentation

- [Docs Home](docs/index.md)
- [Architecture](docs/architecture.md)
- [Quickstart](docs/quickstart.md)
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

## License

Apache-2.0
```

---

# docs/index.md

```md
# ClawGraph Documentation

ClawGraph is a learning-native execution fact graph substrate for OpenClaw-style agents.

It captures immutable execution facts, derives branch-aware execution graphs, attaches typed supervision artifacts, and exports reusable datasets for evaluation and training systems.

## Start here

- [Quickstart](quickstart.md)
- [Architecture](architecture.md)
- [OpenClaw Integration](openclaw_integration.md)
- [Event Protocol](event_protocol.md)
- [Artifact Protocol](artifact_protocol.md)
- [Branching Model](branching.md)
- [Semantic Contract](semantic_contract.md)
- [Supervision Model](supervision.md)
- [Dataset Builders](dataset_builders.md)
- [FAQ](faq.md)
- [Roadmap](roadmap.md)

## Who ClawGraph is for

ClawGraph is for:

- teams running OpenClaw-style agents in production or research
- engineers who want replay and failure analysis without invasive rewrites
- researchers who want learning-ready datasets from real agent execution
- teams with existing backends such as Echo that need a clean capture/export layer

## Mental model

Capture once. Reuse everywhere.

## Key distinction

Most tracing systems are built for monitoring.

ClawGraph is built for learning.
```

---

# docs/architecture.md

```md
# Architecture

## Overview

ClawGraph is a learning-native execution fact graph substrate.

Its architecture is built around a simple idea:

> Capture execution facts once, keep them immutable, derive execution graphs from them, and attach supervision and dataset logic externally.

This lets the same runtime interaction support:

- replay
- failure analysis
- ranking
- supervision
- dataset construction
- downstream training

---

## Layered architecture

```text
┌─────────────────────────────────────────────────────────────┐
│ OpenClaw / Claw-style Agent Runtime                         │
│ model · tool · subagent · user I/O                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Proxy Capture Layer                                      │
│ model proxy · tool proxy · subagent proxy                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Execution Fact Log                                       │
│ append-only immutable execution facts                       │
└─────────────────────────────────────────────────────────────┘
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
┌──────────────────────────┐  ┌───────────────────────────────┐
│ 3a. Semantic Contract    │  │ 3b. Graph/View Builders       │
│ optional runtime signals │  │ session / episode / branch /  │
│ for richer semantics     │  │ execution graph / replay      │
└──────────────────────────┘  └───────────────────────────────┘
               │                             │
               └──────────────┬──────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Artifact Pipeline                                        │
│ supervision · memory · analytics · lineage · export         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Sample Builders                                          │
│ SFT · preference · binary RL · OPD · RM                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Downstream Bridges                                       │
│ Echo · custom trainers · evaluators                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Why proxy-first?

ClawGraph starts with a proxy-first model because adoption matters.

A proxy-first strategy lets teams:

- preserve their current runtime
- redirect model/tool/subagent traffic through ClawGraph
- start collecting useful execution facts immediately
- avoid high upfront instrumentation cost

This is the recommended adoption ladder:

### Step 1: Proxy capture
Collect execution facts with minimal changes.

### Step 2: Context headers
Improve correlation quality by passing stable IDs.

### Step 3: Semantic contract
Add richer runtime signals when higher learning fidelity is needed.

---

## Core layers explained

### 1. Proxy Capture Layer

Responsible for intercepting:

- model requests and responses
- tool requests and responses
- subagent requests and responses
- stream chunks, errors, and timing metadata

The proxy layer is designed for low-friction adoption.

### 2. Execution Fact Log

The fact log is the system’s source of truth.

It stores immutable, append-only execution facts.

This layer is designed for:

- replayability
- versioning
- auditability
- downstream reuse

### 3. Semantic Contract

Some learning-relevant semantics are hard to infer reliably from transport traffic alone.

Examples:

- why a retry happened
- what subgoal was chosen
- why a branch opened
- whether the controller chose continue vs stop

The semantic contract allows runtimes to emit these higher-level semantics explicitly.

### 4. Graph/View Builders

Graph/view builders derive reusable higher-level structures from facts:

- session view
- episode view
- branch tree
- execution graph
- replay timeline

These are **derived**, not immutable source records.

### 5. Artifact Pipeline

Artifacts are external derived objects such as:

- supervision scores
- critiques
- rankings
- distillation targets
- constraints
- memory candidates
- dataset lineage records

Artifacts never mutate historical facts.

### 6. Sample Builders

Sample builders turn graphs + artifacts into dataset outputs.

This keeps training logic decoupled from runtime capture.

---

## Why not just use a tracing system?

A tracing system is usually built for:

- spans
- latency analysis
- monitoring dashboards
- operational debugging

ClawGraph is built for:

- immutable learning-oriented facts
- branch-aware agent execution structure
- typed supervision attachment
- training dataset construction
- sample lineage

This is a different optimization target.

---

## Architectural boundaries

### ClawGraph does

- capture execution facts
- derive execution graphs
- attach typed artifacts
- export datasets and replay views

### ClawGraph does not

- replace the runtime
- prescribe a training algorithm
- enforce a single reward scalar
- require a single judge system

---

## Summary

ClawGraph is best understood as a **learning-native execution fact graph layer**.

Its architecture is designed so that runtime capture, supervision, replay, and training remain loosely coupled while sharing the same immutable execution substrate.
```

---

# docs/quickstart.md

```md
# Quickstart

This guide shows the fastest way to start collecting execution facts with ClawGraph.

## Goal

You will:

1. start the ClawGraph proxy
2. point your OpenClaw-style runtime to the proxy
3. run the agent normally
4. inspect replay
5. export a dataset

---

## Prerequisites

- Python 3.11+
- an existing model endpoint
- an existing tool endpoint
- an OpenClaw-style agent runtime or any tool-using agent that can target custom endpoints

---

## 1. Install ClawGraph

```bash
pip install clawgraph
```

---

## 2. Start the proxy

```bash
clawgraph proxy \
  --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

This starts a local proxy and writes execution facts into the configured store.

---

## 3. Point your runtime to the proxy

Update your runtime configuration:

```yaml
model_endpoint: http://localhost:8080/v1/chat/completions
tool_endpoint: http://localhost:8080/tools
```

No runtime rewrite is required.

---

## 4. Optional: add context headers

If your runtime supports headers or metadata injection, add:

- `x-clawgraph-session-id`
- `x-clawgraph-thread-id`
- `x-clawgraph-task-id`
- `x-clawgraph-user-id`

This improves correlation and graph reconstruction quality.

---

## 5. Run the agent normally

Once configured, use the agent exactly as before.

ClawGraph will capture:

- model request/response lifecycle
- tool request/response lifecycle
- latency, cost, and failure signals
- causal and branch reconstruction inputs

---

## 6. Inspect replay

```bash
clawgraph replay --session latest
```

Depending on configuration, this opens a UI or prints a structured replay summary.

You should be able to inspect:

- user input
- model/tool loops
- inferred or declared branches
- final outputs

---

## 7. Export a dataset

Example: export a preference dataset

```bash
clawgraph export dataset \
  --builder preference \
  --session latest \
  --out ./exports/preference.jsonl
```

Example: export an SFT dataset

```bash
clawgraph export dataset \
  --builder sft \
  --session latest \
  --out ./exports/sft.jsonl
```

---

## What you get immediately in proxy mode

Proxy-first capture gives you:

- immutable execution facts
- replay-ready session history
- branch inference v0
- dataset/export capability

It does **not** automatically give you all high-level learning semantics.

If you later need richer semantics such as explicit retry intent or controller routing, add the semantic contract.

---

## Recommended next steps

- Read [Architecture](architecture.md)
- Read [OpenClaw Integration](openclaw_integration.md)
- Read [Event Protocol](event_protocol.md)
- Read [Artifact Protocol](artifact_protocol.md)
- Read [Semantic Contract](semantic_contract.md)
- Read [Dataset Builders](dataset_builders.md)
```

---

# docs/openclaw_integration.md

```md
# OpenClaw Integration

ClawGraph is designed to be **OpenClaw-first**.

This guide explains how to integrate ClawGraph with OpenClaw-style runtimes using progressively richer modes.

---

## Integration modes

### Mode A: Transparent Proxy

Use this when you want the lowest-friction setup.

You only change the model/tool endpoints to point to ClawGraph.

#### Best for

- quick onboarding
- demos
- early capture
- low instrumentation cost

#### What you get

- execution fact capture
- replay and timeline
- branch inference v0
- export capability

---

### Mode B: Proxy + Context Headers

Use this when you can pass stable metadata.

Recommended headers:

- `x-clawgraph-session-id`
- `x-clawgraph-thread-id`
- `x-clawgraph-task-id`
- `x-clawgraph-user-id`
- `x-clawgraph-parent-id`

#### Best for

- improved correlation
- cleaner episode boundaries
- better sibling branch grouping

---

### Mode C: Proxy + Semantic Contract

Use this when you need richer learning semantics.

Examples of semantic signals:

- plan created
- subgoal selected
- controller route decided
- retry declared
- fallback declared
- branch open reason
- stop reason

#### Best for

- process supervision
- planner/controller learning
- higher-quality dataset construction
- attribution and failure analysis

---

## Recommended rollout path

### Step 1
Start with transparent proxy mode.

### Step 2
Add context headers when you want cleaner graph reconstruction.

### Step 3
Add semantic contract events only where higher learning fidelity matters.

This is the recommended adoption ladder because:

- proxy solves adoption
- semantic contract solves semantic fidelity

---

## Minimum setup example

### Start ClawGraph

```bash
clawgraph proxy \
  --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

### Point OpenClaw to the proxy

```yaml
model_endpoint: http://localhost:8080/v1/chat/completions
tool_endpoint: http://localhost:8080/tools
```

That is enough to begin collecting useful execution facts.

---

## What ClawGraph can infer in proxy-only mode

Proxy-only mode can reconstruct a large amount of execution structure from:

- request/response ordering
- tool call identifiers
- parent-child request correlations
- stream lifecycle boundaries
- usage and failure metadata

It may also infer candidate semantics such as:

- probable retries
- probable fallbacks
- likely repair chains
- subagent branch groupings

These are **derived views**, not immutable source facts.

---

## What should come from the runtime explicitly

The following are usually better provided through the semantic contract:

- planner/subgoal boundaries
- retry reason
- controller stop/continue decision
- explicit branch reason
- confidence or uncertainty estimate
- human takeover trigger

---

## Separation of responsibilities

### OpenClaw runtime
Responsible for execution.

### ClawGraph
Responsible for capture, graph derivation, artifact organization, replay, and export.

### Downstream systems
Responsible for evaluation, training, and consumption.

---

## Example user stories

### A team starting with zero runtime rewrites
They adopt proxy mode first, get replay and export immediately, and add semantic events later.

### A platform team and a research team working together
The platform team maintains low-intrusion proxy capture. The research team adds semantic contract signals for better learning quality.

### A team beginning with replay/debug only
They start with proxy mode for replay, then add judges and sample builders, and only later add runtime semantics to increase learning fidelity.
```

---

# docs/event_protocol.md

```md
# Event Protocol

The event protocol defines the immutable execution fact layer of ClawGraph.

This protocol is the foundation of the entire system.

If facts are not stable, replay, supervision, ranking, and datasets will drift apart over time.

---

## Design goals

The protocol is designed to be:

- immutable
- append-only
- replayable
- versioned
- runtime-agnostic
- suitable for graph derivation and learning reuse

---

## Why facts, not spans?

ClawGraph intentionally uses the term **execution fact** instead of span or trace event.

The goal is not only monitoring.

The goal is to preserve runtime behavior in a reusable form for:

- replay
- judgment
- ranking
- dataset construction
- training

---

## Fact envelope

Every fact uses a stable envelope.

```json
{
  "fact_id": "fact_01",
  "session_id": "sess_01",
  "episode_id": "epi_01",
  "thread_id": "thr_01",
  "branch_id": "br_01",
  "turn_id": "turn_01",
  "step_id": "step_01",
  "fact_type": "tool_request_started",
  "actor": "tool_proxy",
  "timestamp_ms": 1710000000000,
  "prev_fact_id": "fact_prev",
  "causal_parent_ids": ["fact_parent_1"],
  "supersedes_fact_id": null,
  "payload_version": "v1",
  "payload": {},
  "metrics": {
    "latency_ms": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cost_usd": 0.0
  },
  "risk": {
    "level": "low",
    "tags": []
  },
  "context": {
    "runtime": "openclaw",
    "runtime_version": "x.y.z"
  }
}
```

---

## Required fields

### `fact_id`
Globally unique identifier for the fact.

### `session_id`
Groups a longer-lived interaction context.

### `episode_id`
Groups a task attempt or goal boundary within a session.

### `branch_id`
Associates the fact with a branch.

### `fact_type`
Declares the type of execution fact.

### `timestamp_ms`
Absolute creation time.

### `payload_version`
Version of the payload schema.

### `payload`
Type-specific content.

---

## Fact types

### Lifecycle facts
- `session_opened`
- `session_closed`
- `episode_opened`
- `episode_closed`
- `branch_opened`
- `branch_closed`

### User I/O facts
- `user_message_received`
- `intermediate_update_sent`
- `final_response_sent`

### Model facts
- `model_request_started`
- `model_stream_chunk_received`
- `model_response_finished`
- `model_response_failed`

### Tool facts
- `tool_request_started`
- `tool_response_finished`
- `tool_response_failed`

### Subagent facts
- `subagent_request_started`
- `subagent_response_finished`
- `subagent_response_failed`

### Observation facts
- `env_observation_received`
- `tool_result_received`

### Semantic bridge facts
- `semantic_event_logged`

### Artifact/export facts
- `artifact_emitted`
- `dataset_exported`

---

## Causality fields

### `prev_fact_id`
Simple timeline predecessor.

### `causal_parent_ids`
Facts that materially caused this fact.

### `supersedes_fact_id`
Optional replacement relationship for explicit correction semantics.

ClawGraph distinguishes timeline order from causality because agent behavior is rarely a simple list.

---

## Metrics and risk

The protocol reserves common fields for:

- token counts
- latency
- monetary cost
- risk tags

These are useful for:

- replay context
- cost-aware analysis
- constraint artifacts
- downstream sample selection

---

## Versioning

The event protocol should version:

- envelope schema
- payload schema
- type definitions

The recommended rule is:

- avoid breaking envelope stability early
- evolve type payloads through payload versioning
- derive richer graph semantics outside the fact log when possible

---

## Invariants

ClawGraph should preserve these invariants:

1. facts are append-only
2. facts are not silently rewritten
3. derived graph semantics do not overwrite raw facts
4. downstream systems must be able to re-materialize views from facts alone

---

## Why this protocol matters

A stable fact protocol is what allows one runtime interaction to be reused later by:

- replay tools
- judges
- ranking systems
- sample builders
- trainers

Without a stable fact protocol, everything else becomes fragile.
```

---

# docs/artifact_protocol.md

```md
# Artifact Protocol

The artifact protocol defines how ClawGraph attaches supervision, lineage, and other derived information to execution facts and graph objects.

Artifacts are external, typed, and versioned.

They must never mutate historical facts.

---

## Why artifacts exist

Runtime facts should stay clean and immutable.

But learning systems need much more than facts alone.

They need:

- scores
- labels
- rankings
- critiques
- constraints
- distillation targets
- dataset lineage
- memory candidates

The artifact protocol exists to carry all of these in a structured way.

---

## Artifact envelope

```json
{
  "artifact_id": "art_01",
  "artifact_type": "ranking",
  "target_ref": "branch:br_02",
  "source_type": "llm_judge",
  "source_name": "judge_v4",
  "source_version": "2026-03-17",
  "created_at_ms": 1710000000000,
  "confidence": 0.84,
  "supersedes": null,
  "status": "active",
  "metadata": {},
  "payload": {}
}
```

---

## Required fields

### `artifact_id`
Globally unique artifact identifier.

### `artifact_type`
Declares the artifact category.

### `target_ref`
Points to the object being annotated.

### `source_type`
Describes the source family, for example:

- `human_review`
- `llm_judge`
- `teacher_model`
- `verifier`
- `builder`
- `exporter`

### `source_name`
Concrete generator name.

### `source_version`
Version of the source system or prompt.

### `created_at_ms`
Artifact creation timestamp.

### `status`
Current lifecycle state.

### `payload`
Artifact-specific content.

---

## Target reference model

Artifacts can target different graph objects.

Supported reference shapes should include:

- `session:<id>`
- `episode:<id>`
- `branch:<id>`
- `fact:<id>`
- `step:<id>`
- `edge:<id>`
- `response:<id>`

This makes it possible to attach supervision at multiple levels.

---

## Artifact families

### Supervision artifacts
- `score`
- `label`
- `ranking`
- `critique`
- `distillation`
- `constraint`

### Memory artifacts
- `episodic_candidate`
- `skill_candidate`
- `preference_overlay`

### Lineage artifacts
- `builder_output`
- `export_record`

---

## Artifact lifecycle

Recommended lifecycle states:

- `draft`
- `active`
- `superseded`
- `deprecated`
- `invalid`

This allows:

- judge upgrades
- human corrections
- invalidation of bad artifacts
- version-aware dataset reproduction

---

## Provenance

Artifacts must carry enough provenance to answer:

- who generated this?
- with what version?
- when?
- on what target?
- with what confidence?
- did it replace an earlier artifact?

This is critical for reproducibility.

---

## Conflicts are allowed

ClawGraph does not require all artifacts to agree.

Examples:

- a human review may disagree with an LLM judge
- a ranking may conflict with a score
- a cost constraint may veto an otherwise good branch

Conflicts should be preserved, not hidden.

---

## Why this protocol matters

Without a strong artifact protocol:

- builders cannot be trusted
- dataset lineage becomes unclear
- judge evolution pollutes historical outputs
- replay and learning views drift apart

A strong artifact protocol makes ClawGraph usable as a real learning substrate rather than a logging utility.
```

---

# docs/branching.md

```md
# Branching Model

Branching is first-class in ClawGraph.

This is one of the main ways ClawGraph differs from ordinary tracing systems.

A message list is not enough to represent real agent behavior.

Agent execution often contains:

- retries
- repairs
- fallbacks
- sibling alternatives
- subagent delegation

ClawGraph models these explicitly.

---

## Why branching matters

Learning systems care deeply about branch structure because branch structure determines:

- what counts as a retry
- what counts as repair
- which sibling branch was better
- how failure propagation happened
- how preference and ranking samples should be built

Without branching, most learning-oriented replay and dataset logic becomes shallow.

---

## Core branch types

### v1 branch types
- `mainline`
- `retry`
- `fallback`
- `repair`
- `subagent`

### Future branch types
- `exploration`
- `counterfactual`
- `human_takeover`
- `tool_replan`

---

## Branch schema

Example branch object:

```json
{
  "branch_id": "br_02",
  "episode_id": "epi_01",
  "parent_branch_id": "br_01",
  "branch_type": "retry",
  "declared_or_inferred": "inferred",
  "spawned_from_fact_id": "fact_45",
  "open_reason": "tool_failure_retry",
  "close_reason": "completed",
  "status": "closed",
  "confidence": 0.86
}
```

---

## Branch state model

Suggested states:

- `open`
- `active`
- `suspended`
- `merged`
- `abandoned`
- `closed`

This allows replay and ranking logic to distinguish:

- live branches
- failed branches
- merged repair branches
- abandoned paths

---

## Inferred vs declared

A branch may be:

### `inferred`
Derived heuristically from proxy-level execution facts.

### `declared`
Explicitly emitted by the runtime through the semantic contract.

This distinction is important because:

- inferred branches are useful for early adoption
- declared branches provide higher semantic fidelity

---

## Parent-child rules

Every branch should have:

- a stable `branch_id`
- an optional `parent_branch_id`
- a `spawned_from_fact_id`

This allows tree reconstruction and sibling comparison.

---

## Merge and close semantics

Not every branch simply succeeds or fails.

A branch may:

- finish independently
- be abandoned
- merge into a mainline branch
- trigger a repair continuation

Branch close semantics should be explicit in derived views and, when possible, in declared semantics.

---

## Why ClawGraph emphasizes branching

Most tracing systems are good at timing and request flow.

They are not strong at representing:

- repair chains
- branch competition
- chosen vs rejected paths
- subagent branching

ClawGraph treats branching as a core execution structure because branch structure is essential for learning-oriented replay, ranking, and dataset construction.
```

---

# docs/semantic_contract.md

```md
# Semantic Contract

The semantic contract is ClawGraph’s optional runtime semantics interface.

It exists to solve a practical problem:

Proxy-only capture is excellent for adoption, but it cannot always recover the higher-level learning semantics that advanced users need.

---

## Why a semantic contract exists

From transport traffic alone, it is difficult to infer some important agent semantics reliably.

Examples:

- why a retry happened
- which subgoal was chosen
- whether the controller decided continue or stop
- why a branch opened
- whether confidence was low

These semantics are often critical for:

- process supervision
- planner/controller learning
- attribution
- higher-quality dataset building

---

## What the semantic contract is

The semantic contract is an optional protocol through which a runtime can emit richer learning-relevant semantics.

It complements proxy-first capture rather than replacing it.

---

## Recommended semantic event types

ClawGraph should support events such as:

- `plan_created`
- `subgoal_selected`
- `controller_route_decided`
- `branch_open_declared`
- `branch_close_declared`
- `retry_declared`
- `fallback_declared`
- `stop_decision_declared`
- `uncertainty_estimated`
- `human_help_requested`

---

## Example semantic event

```json
{
  "semantic_id": "sem_01",
  "semantic_type": "retry_declared",
  "session_id": "sess_01",
  "episode_id": "epi_01",
  "branch_id": "br_02",
  "target_ref": "fact:fact_44",
  "source": "openclaw_runtime",
  "source_version": "0.9.0",
  "timestamp_ms": 1710000000000,
  "payload": {
    "reason": "tool_timeout",
    "tool_name": "exec"
  }
}
```

---

## Design principles

### 1. Optional
The semantic contract is not required for basic ClawGraph usage.

### 2. Additive
Semantic events add information; they do not rewrite historical proxy facts.

### 3. Learning-oriented
The contract exists specifically to improve semantic fidelity for learning and evaluation.

### 4. Runtime-friendly
The contract should be easy for runtimes to adopt incrementally.

---

## Recommended adoption path

### Step 1
Start with proxy-only capture.

### Step 2
Add context headers.

### Step 3
Add selected semantic events only where learning quality materially improves.

Examples of good first semantic additions:

- retry reason
- branch-open reason
- stop decision
- controller route decision

---

## Why this matters

The semantic contract is how ClawGraph avoids the semantic ceiling of proxy-only capture while preserving low-friction adoption.

This is one of the project’s key architectural ideas:

**proxy solves adoption, semantic contract solves semantic fidelity.**
```

---

# docs/supervision.md

```md
# Supervision Model

ClawGraph uses a **supervision model**, not a single reward model.

This is intentional.

Real-world learning systems use many kinds of signals:

- human review
- LLM-as-a-judge
- next-state hindsight
- rankings
- critiques
- distillation
- cost and safety constraints

ClawGraph models these as typed external artifacts.

---

## Why not a single reward scalar?

A single scalar reward is often too narrow for real agent learning.

Examples:

- a human may provide critique, not a score
- a judge may provide pairwise preference, not pointwise labels
- a teacher may provide rewritten targets or logits
- a safety system may produce vetoes, not soft rewards

A learning substrate must remain compatible with all of these.

---

## Supervision families

### Outcome supervision
Signals about final task quality.

Examples:

- success/failure
- correctness score
- completion score
- user satisfaction

### Process supervision
Signals about intermediate behavior quality.

Examples:

- planning quality
- tool choice quality
- retry quality
- stop/continue quality

### Preference supervision
Signals comparing multiple candidates.

Examples:

- branch A is better than branch B
- chosen vs rejected path
- listwise ordering

### Distillation supervision
Signals from a teacher or stronger model.

Examples:

- rewritten answer
- teacher plan
- token logprobs
- hindsight-gated target

### Constraint supervision
Signals representing boundaries or penalties.

Examples:

- safety violation
- privacy violation
- high cost
- high latency
- policy veto

---

## Why artifacts matter here

ClawGraph stores supervision externally as artifacts so that:

- historical facts stay clean
- supervision can evolve without corrupting old data
- multiple judges can coexist
- multiple dataset builders can reuse the same trajectories

---

## Key supervision principle

Do not collapse all supervision into one score too early.

Keep signals typed, explicit, and versioned.

This is what allows one execution graph to support multiple downstream learning recipes.
```

---

# docs/dataset_builders.md

```md
# Dataset Builders

ClawGraph separates:

- execution capture
- supervision attachment
- dataset construction

This allows the same captured execution graphs to be reused across multiple training strategies.

---

## What a builder does

A sample builder consumes:

- trajectory views
- artifact views
- optional memory overlays
- optional structured selection filters

and emits a user-defined dataset.

Pseudo-interface:

```python
build(
    trajectory_view,
    artifact_view,
    memory_view=None,
    selection_query=None,
    context=None,
)
```

---

## Why builders are important

Builders are one of ClawGraph’s core abstractions.

They allow the same execution graph to be transformed into:

- SFT samples
- preference pairs
- binary RL samples
- OPD-style distillation samples
- process reward model samples

without requiring the runtime to be re-instrumented.

---

## Built-in builder families

### SFT builder
Produces examples such as:

- accepted response targets
- corrected response targets
- teacher-rewritten targets

### Preference builder
Produces:

- chosen/rejected pairs
- sibling branch comparisons
- ranked candidate groups

### Binary RL builder
Produces tuples aligned with binary or scalar supervision.

### OPD builder
Produces hindsight-guided or teacher-gated distillation datasets.

### Process RM builder
Produces step-level or branch-level quality examples.

---

## Structured selection, not DSL

ClawGraph v1 does not require a DSL.

Instead, it should support structured selection objects and builder filters.

Example idea:

```python
BranchSelector(
    branch_type="retry",
    final_outcome="fail",
    has_artifact_type="critique",
)
```

This keeps the system simpler while the graph and artifact protocols stabilize.

---

## Sample lineage

Every exported sample should be traceable back to:

- the source graph objects
- the source artifacts
- the builder name and version
- the export time

This is essential for reproducibility and trust.

---

## Design principle

Builders are how ClawGraph becomes more than a capture tool.

They turn ClawGraph into a reusable learning data substrate.
```

---

# docs/faq.md

```md
# FAQ

## Is ClawGraph a new agent runtime?

No. ClawGraph sits underneath a runtime as a capture, graph, supervision, and export layer.

## Does ClawGraph replace OpenClaw?

No. OpenClaw remains the runtime. ClawGraph captures and structures execution for replay and learning reuse.

## Do I need to rewrite my runtime?

Not in the default path. ClawGraph is designed for proxy-first adoption.

## Why not just use tracing or observability tools?

Because most tracing systems are built for monitoring. ClawGraph is built for learning.

It emphasizes immutable facts, branch-aware execution structure, typed supervision, and dataset reuse.

## Is ClawGraph tied to a specific training algorithm?

No. It is training-agnostic.

## Does ClawGraph define reward?

No single reward scalar is required. ClawGraph models supervision as typed artifacts.

## Can I use human review, LLM judges, and distillation together?

Yes. That is one of the main goals of the artifact model.

## Can I use ClawGraph only for replay/debugging?

Yes. You can adopt it first for replay and analysis, then later add supervision and dataset builders.

## Why keep facts immutable?

Because learning logic changes quickly. Immutable facts keep old runs reusable even when prompts, judges, or dataset strategies evolve.

## What does the semantic contract do?

It lets runtimes add higher-fidelity learning semantics such as retry reasons, branch-open reasons, and controller decisions.

## Does ClawGraph support DSL queries?

Not as a first requirement. v1 should focus on structured selectors and builder filters.

## Can ClawGraph export to an existing backend?

Yes. The export layer is designed to feed downstream systems such as Echo or custom training stacks.
```

---

# docs/roadmap.md

```md
# Roadmap

This roadmap describes the intended evolution of ClawGraph.

---

## Phase 1: Core substrate

Focus:

- proxy-first capture
- immutable fact protocol
- sqlite-backed fact storage
- session / episode / branch / replay views
- artifact protocol v1
- SFT / preference / binary RL builders
- replay and export CLI

Goal:

Prove that real runtime traffic can be turned into stable, reusable execution graphs.

---

## Phase 2: Branch-aware learning workflows

Focus:

- better branch inference
- branch overlay UI
- richer artifact families
- sample lineage
- replay with artifact overlays
- Echo bridge improvements

Goal:

Make ClawGraph visibly better than generic tracing for learning workflows.

---

## Phase 3: Semantic fidelity expansion

Focus:

- semantic contract v1
- planner/controller runtime semantics
- retry/fallback declaration support
- stop/continue and uncertainty semantics

Goal:

Raise the semantic ceiling beyond proxy-only capture.

---

## Phase 4: Broader builder ecosystem

Focus:

- OPD builder
- process RM builder
- branch comparison builders
- selection/query API improvements

Goal:

Strengthen ClawGraph as a learning data substrate.

---

## Phase 5: Richer UX and ecosystem growth

Focus:

- learning replay cockpit
- artifact overlay explorer
- builder plugin ecosystem
- more downstream bridges

Goal:

Turn ClawGraph into a reusable platform rather than a single-purpose capture tool.
```

