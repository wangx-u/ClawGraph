# ClawGraph

<p align="center">
  <img src="docs/clawgraph-logo.png" alt="ClawGraph logo" width="160">
</p>

### Immutable, branch-aware execution graphs for OpenClaw-style agents

ClawGraph sits between your runtime and your training stack. It captures real
agent execution once, keeps facts immutable, lets you attach supervision later,
and exports reusable datasets for SFT, preference learning, binary RL, async RL,
and distillation.

> Most tracing systems are built for monitoring. ClawGraph is built for learning.

## Why teams use ClawGraph

- **Proxy-first adoption**: point model and tool traffic at ClawGraph before
  you change runtime code.
- **Learning-native observability**: inspect sessions, requests, branches,
  artifacts, and export readiness from the same captured run.
- **Branch-aware execution**: retries, fallbacks, repairs, and subagents are
  first-class instead of hidden in flat logs.
- **Reusable supervision**: keep facts immutable and attach scores, labels,
  rankings, and critiques as separate typed artifacts.
- **Downstream-ready datasets**: export the same run into SFT, preference, and
  binary RL builders with lineage-aware manifests.

## In one sentence

ClawGraph turns real OpenClaw-style agent runs into reusable learning data
without forcing you to rewrite the runtime first.

## 5-minute quickstart

Install and inspect a complete seeded session locally:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

clawgraph bootstrap openclaw --store sqlite:///clawgraph.db
clawgraph list sessions
clawgraph inspect session --session latest
clawgraph replay --session latest
clawgraph readiness --session latest --builder preference
clawgraph export dataset --builder preference --session latest --dry-run
```

When you are ready to connect a real runtime:

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

## Choose your path

| If you want to... | Start here |
| --- | --- |
| Follow one guided path from first run to export | [`docs/guides/fifteen_minute_path.md`](docs/guides/fifteen_minute_path.md) |
| See ClawGraph working end to end in one session | [`docs/guides/quickstart.md`](docs/guides/quickstart.md) |
| Connect an existing OpenClaw-style runtime | [`docs/guides/openclaw_integration.md`](docs/guides/openclaw_integration.md) |
| Understand which command to run next for your role | [`docs/guides/user_stories.md`](docs/guides/user_stories.md) |
| Inspect failures before exporting training data | [`docs/guides/replay_and_debug.md`](docs/guides/replay_and_debug.md) |
| Generate datasets for training | [`docs/guides/dataset_builders.md`](docs/guides/dataset_builders.md) |
| Go from exported datasets into async RL | [`docs/guides/export_to_async_rl.md`](docs/guides/export_to_async_rl.md) |

## What you can do today

### 1. Capture real traffic

- Run `clawgraph proxy`
- Route model and tool traffic through ClawGraph
- Add stable ids later with `x-clawgraph-session-id`, `x-clawgraph-run-id`,
  `x-clawgraph-request-id`, and `x-clawgraph-user-id`

### 2. Inspect before you train

- `clawgraph list sessions`
- `clawgraph list requests --session latest`
- `clawgraph inspect session --session latest`
- `clawgraph inspect request --session latest --request-id latest`
- `clawgraph inspect branch --session latest`
- `clawgraph replay --session latest`

### 3. Attach supervision without mutating facts

- `clawgraph artifact bootstrap --template openclaw-defaults --session latest`
- `clawgraph artifact list --session latest --latest-only`
- `clawgraph semantic append ...` for retry, fallback, and routing signals

### 4. Export training-ready datasets

- `clawgraph readiness --session latest --builder sft`
- `clawgraph readiness --session latest --builder preference`
- `clawgraph readiness --session latest --builder binary_rl`
- `clawgraph export dataset --builder sft --session latest --out exports/sft.jsonl`
- `clawgraph export dataset --builder preference --session latest --out exports/preference.jsonl`
- `clawgraph export dataset --builder binary_rl --session latest --out exports/binary_rl.jsonl`

Each export also writes a manifest:

- `*.jsonl.manifest.json`

## How ClawGraph fits into the stack

```text
OpenClaw / Claw-style Agent Runtime
(model, tools, subagents, user I/O)
                    |
                    v
              ClawGraph Proxy
                    |
                    v
           Immutable Fact Log
                    |
        +-----------+------------+
        |                        |
        v                        v
  Semantic Contract        Graph / View Builders
        +-----------+------------+
                    |
                    v
              Artifact Engine
                    |
                    v
              Dataset Builders
                    |
                    v
         Async RL / Distill Bridges
```

The design rule is simple:

1. capture execution facts once
2. never mutate those facts
3. derive replay and branch views from them
4. attach supervision externally
5. export datasets through reproducible builders

## What ClawGraph is

- a learning-native execution substrate
- a proxy-first capture layer for OpenClaw-style runtimes
- a branch-aware replay and inspection system
- a typed artifact layer for post hoc supervision
- a reproducible dataset export layer

## What ClawGraph is not

- a new agent runtime
- a trainer
- a fixed reward system
- a dashboard-first observability product
- tied to a single RL, SFT, DPO, or distillation recipe

## Commands you will use most

- `clawgraph bootstrap`
- `clawgraph proxy`
- `clawgraph list`
- `clawgraph replay`
- `clawgraph inspect`
- `clawgraph semantic append`
- `clawgraph artifact bootstrap`
- `clawgraph artifact append`
- `clawgraph artifact list`
- `clawgraph readiness`
- `clawgraph export dataset`

## Documentation

- Start here: [`docs/guides/start_here.md`](docs/guides/start_here.md)
- 15-minute path: [`docs/guides/fifteen_minute_path.md`](docs/guides/fifteen_minute_path.md)
- Quickstart: [`docs/guides/quickstart.md`](docs/guides/quickstart.md)
- OpenClaw integration: [`docs/guides/openclaw_integration.md`](docs/guides/openclaw_integration.md)
- User stories: [`docs/guides/user_stories.md`](docs/guides/user_stories.md)
- Dataset builders: [`docs/guides/dataset_builders.md`](docs/guides/dataset_builders.md)
- CLI reference: [`docs/reference/cli_reference.md`](docs/reference/cli_reference.md)
- Examples: [`examples/README.md`](examples/README.md)
- Docs home: [`docs/index.md`](docs/index.md)

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

## Current focus

The current ClawGraph release focuses on:

- proxy-first capture
- immutable fact protocol
- session, request, branch, and replay views
- typed artifact protocol
- reusable dataset builders
- export bridges to downstream training systems

## More entry points

- Roadmap: [`ROADMAP.md`](ROADMAP.md)
- Backlog: [`BACKLOG.md`](BACKLOG.md)
- Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Event protocol: [`docs/reference/event_protocol.md`](docs/reference/event_protocol.md)
- Branching model: [`docs/concepts/branching.md`](docs/concepts/branching.md)
- Artifact protocol: [`docs/concepts/artifact_protocol.md`](docs/concepts/artifact_protocol.md)
- Semantic contract: [`docs/concepts/semantic_contract.md`](docs/concepts/semantic_contract.md)
