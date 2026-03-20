# ClawGraph

<p align="center">
  <img src="docs/clawgraph-logo.png" alt="ClawGraph logo" width="160">
</p>

### Immutable, branch-aware execution graphs for OpenClaw-style agents

ClawGraph captures real agent execution once, keeps facts immutable, attaches
supervision later, and exports reusable datasets for SFT, preference learning,
binary RL, async RL, and distillation.

> Most tracing systems are built for monitoring. ClawGraph is built for learning.

[English](README.md) | [简体中文](README.zh-CN.md)

## Why teams use it

- Proxy-first adoption for existing OpenClaw-style runtimes
- Replay, inspect, and readiness from the same captured run
- Branch-aware execution for retries, fallbacks, and subagents
- Canonical outputs for streaming, tool calls, and downstream export

## 5-minute quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

clawgraph bootstrap openclaw --store sqlite:///clawgraph.db
clawgraph inspect session --session latest
clawgraph replay --session latest
clawgraph readiness --session latest --builder preference
clawgraph export dataset --builder preference --session latest --dry-run
```

Connect a real runtime later:

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

## Choose your path

| Goal | Link |
| --- | --- |
| Fastest first run | [`docs/guides/start_here.md`](docs/guides/start_here.md) |
| One guided path from first run to export | [`docs/guides/fifteen_minute_path.md`](docs/guides/fifteen_minute_path.md) |
| Connect OpenClaw or another OpenAI-compatible runtime | [`docs/guides/openclaw_integration.md`](docs/guides/openclaw_integration.md) |
| Inspect replay, branches, and readiness | [`docs/guides/replay_and_debug.md`](docs/guides/replay_and_debug.md) |
| Export datasets for training | [`docs/guides/dataset_builders.md`](docs/guides/dataset_builders.md) |
| Chinese docs | [`docs/zh-CN/README.md`](docs/zh-CN/README.md) |

## Core commands

- `clawgraph bootstrap`
- `clawgraph proxy`
- `clawgraph list readiness`
- `clawgraph replay`
- `clawgraph inspect`
- `clawgraph pipeline run`
- `clawgraph readiness`
- `clawgraph export dataset`

## Docs

- Start here: [`docs/guides/start_here.md`](docs/guides/start_here.md)
- 15-minute path: [`docs/guides/fifteen_minute_path.md`](docs/guides/fifteen_minute_path.md)
- OpenClaw integration: [`docs/guides/openclaw_integration.md`](docs/guides/openclaw_integration.md)
- Workflow overview: [`docs/guides/workflow_overview.md`](docs/guides/workflow_overview.md)
- Dataset builders: [`docs/guides/dataset_builders.md`](docs/guides/dataset_builders.md)
- Chinese docs: [`docs/zh-CN/README.md`](docs/zh-CN/README.md)
- Examples: [`examples/README.md`](examples/README.md)
- CLI reference: [`docs/reference/cli_reference.md`](docs/reference/cli_reference.md)

ClawGraph is a learning-native execution substrate. It is not a new agent
runtime, not a trainer, and not tied to one RL recipe.

## Project files

- Roadmap: [`ROADMAP.md`](ROADMAP.md)
- Backlog: [`BACKLOG.md`](BACKLOG.md)
- Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md)
