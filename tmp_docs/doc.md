

下面继续，直接补到**可以开工**的程度：

1. **docs 站技术选型建议**
2. **docs 站导航/配置文件**
3. **仓库初始化文件**
4. **首批占位文件清单**
5. **适合 vibe coding 的首轮任务拆解**

我会默认你现在用一个最稳、最轻、最适合快速起站的方案。

---

# 一、docs 站技术选型建议

我建议优先选：

## **VitePress**

原因很直接：

* 轻
* 上手快
* Markdown 原生体验好
* 文档站结构清晰
* 很适合“协议文档 + 架构文档 + 指南”
* 对 vibe coding 很友好，生成和修改成本低

### 不优先选的原因

#### Docusaurus

功能强，但首轮略重，配置噪音更大。

#### Nextra

更偏内容网站/产品文档，也可以，但信息架构控制感不如 VitePress 稳。

所以我建议：

## 首轮 docs 站：**VitePress**

## 后续如果要官网化，再考虑补 marketing site

---

# 二、推荐的仓库结构（最终落地版）

```text
clawgraph/
├── README.md
├── LICENSE
├── pyproject.toml
├── Makefile
├── .gitignore
├── .env.example
├── docs/
│   ├── index.md
│   ├── overview/
│   │   ├── what_is_clawgraph.md
│   │   ├── architecture.md
│   │   ├── why_not_tracing.md
│   │   └── roadmap.md
│   ├── concepts/
│   │   ├── execution_facts.md
│   │   ├── execution_graph.md
│   │   ├── branching.md
│   │   ├── artifact_protocol.md
│   │   ├── semantic_contract.md
│   │   └── supervision_model.md
│   ├── guides/
│   │   ├── quickstart.md
│   │   ├── openclaw_integration.md
│   │   ├── proxy_mode.md
│   │   ├── semantic_mode.md
│   │   ├── replay_and_debug.md
│   │   ├── dataset_builders.md
│   │   ├── export_to_echo.md
│   │   └── custom_artifacts_and_builders.md
│   ├── reference/
│   │   ├── event_protocol.md
│   │   ├── branch_schema.md
│   │   ├── artifact_schema.md
│   │   ├── semantic_schema.md
│   │   ├── builder_interface.md
│   │   ├── cli_reference.md
│   │   └── faq.md
│   └── .vitepress/
│       └── config.ts
│
├── examples/
│   ├── openclaw_proxy_minimal/
│   ├── openclaw_proxy_with_headers/
│   ├── openclaw_with_semantic_contract/
│   ├── replay_demo/
│   └── echo_bridge_demo/
│
├── clawgraph/
│   ├── __init__.py
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
│
└── tests/
```

---

# 三、VitePress 配置文件

下面这个配置可以直接作为 `docs/.vitepress/config.ts` 初稿。

```ts
import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'ClawGraph',
  description:
    'Immutable, branch-aware execution graphs for OpenClaw-style agents.',

  themeConfig: {
    nav: [
      { text: 'Overview', link: '/overview/what_is_clawgraph' },
      { text: 'Concepts', link: '/concepts/execution_facts' },
      { text: 'Guides', link: '/guides/quickstart' },
      { text: 'Reference', link: '/reference/event_protocol' },
      { text: 'GitHub', link: 'https://github.com/your-org/clawgraph' }
    ],

    sidebar: {
      '/overview/': [
        {
          text: 'Overview',
          items: [
            { text: 'What is ClawGraph', link: '/overview/what_is_clawgraph' },
            { text: 'Architecture', link: '/overview/architecture' },
            { text: 'Why not tracing', link: '/overview/why_not_tracing' },
            { text: 'Roadmap', link: '/overview/roadmap' }
          ]
        }
      ],
      '/concepts/': [
        {
          text: 'Core Concepts',
          items: [
            { text: 'Execution Facts', link: '/concepts/execution_facts' },
            { text: 'Execution Graph', link: '/concepts/execution_graph' },
            { text: 'Branching Model', link: '/concepts/branching' },
            { text: 'Artifact Protocol', link: '/concepts/artifact_protocol' },
            { text: 'Semantic Contract', link: '/concepts/semantic_contract' },
            { text: 'Supervision Model', link: '/concepts/supervision_model' }
          ]
        }
      ],
      '/guides/': [
        {
          text: 'Guides',
          items: [
            { text: 'Quickstart', link: '/guides/quickstart' },
            { text: 'OpenClaw Integration', link: '/guides/openclaw_integration' },
            { text: 'Proxy Mode', link: '/guides/proxy_mode' },
            { text: 'Semantic Mode', link: '/guides/semantic_mode' },
            { text: 'Replay and Debug', link: '/guides/replay_and_debug' },
            { text: 'Dataset Builders', link: '/guides/dataset_builders' },
            { text: 'Export to Echo', link: '/guides/export_to_echo' },
            {
              text: 'Custom Artifacts and Builders',
              link: '/guides/custom_artifacts_and_builders'
            }
          ]
        }
      ],
      '/reference/': [
        {
          text: 'Reference',
          items: [
            { text: 'Event Protocol', link: '/reference/event_protocol' },
            { text: 'Branch Schema', link: '/reference/branch_schema' },
            { text: 'Artifact Schema', link: '/reference/artifact_schema' },
            { text: 'Semantic Schema', link: '/reference/semantic_schema' },
            { text: 'Builder Interface', link: '/reference/builder_interface' },
            { text: 'CLI Reference', link: '/reference/cli_reference' },
            { text: 'FAQ', link: '/reference/faq' }
          ]
        }
      ]
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/your-org/clawgraph' }
    ],

    search: {
      provider: 'local'
    }
  }
})
```

---

# 四、docs 首页文件初稿

这个版本更适合 VitePress 首页风格，保存成 `docs/index.md`。

```md
---
layout: home

hero:
  name: ClawGraph
  text: Immutable, branch-aware execution graphs for OpenClaw-style agents
  tagline: Proxy-first capture for real agent execution. Replay, judge, rank, and build datasets from the same source of truth.
  actions:
    - theme: brand
      text: Get Started
      link: /guides/quickstart
    - theme: alt
      text: Read Architecture
      link: /overview/architecture
    - theme: alt
      text: View Protocols
      link: /reference/event_protocol

features:
  - title: Built for learning, not dashboards
    details: Most tracing systems are built for monitoring. ClawGraph is built for replay, judgment, ranking, dataset construction, and training reuse.
  - title: Proxy-first adoption
    details: Start by routing model and tool traffic through ClawGraph. No runtime rewrite required. Add richer semantics only when you need them.
  - title: Branch-aware execution graphs
    details: Retries, fallbacks, repairs, and subagents are first-class. ClawGraph models execution as reusable graph structure, not flat logs.
  - title: Typed supervision artifacts
    details: Scores, labels, rankings, critiques, constraints, and distillation targets live outside immutable facts as versioned artifacts.
  - title: User-defined dataset builders
    details: Turn the same execution graph into SFT, preference, binary RL, or custom datasets without re-instrumenting your runtime.
  - title: Downstream-ready
    details: Export replay, datasets, and lineage into systems like Echo or your own training and evaluation stack.
---

> **Most tracing systems are built for monitoring. ClawGraph is built for learning.**
```

---

# 五、建议新增的 overview 页面内容

## `docs/overview/what_is_clawgraph.md`

```md
# What is ClawGraph?

ClawGraph is a learning-native execution fact graph substrate for OpenClaw-style agents.

It captures immutable execution facts from real agent runs, derives branch-aware execution graphs, attaches typed supervision artifacts, and exports reusable data for replay, evaluation, ranking, and training.

## The layer it occupies

ClawGraph sits between:

- **runtime execution**
- **learning/evaluation/export systems**

It does not replace the runtime, and it does not prescribe a single training algorithm.

## The core promise

Capture execution once. Reuse it everywhere.
```

---

## `docs/overview/why_not_tracing.md`

```md
# Why not tracing?

Traditional tracing systems are optimized for:

- operational visibility
- latency analysis
- request flow debugging
- dashboards and alerts

ClawGraph is optimized for:

- immutable execution facts
- branch-aware execution structure
- typed supervision attachment
- dataset construction
- learning replay
- downstream training reuse

This is why ClawGraph should not be understood as “agent tracing with nicer visuals”.

It is a learning substrate.
```

---

# 六、建议新增的 concepts 页面内容

## `docs/concepts/execution_facts.md`

```md
# Execution Facts

Execution facts are the immutable source records of ClawGraph.

They are append-only records of what actually happened during runtime execution.

Examples include:

- user message received
- model request started
- model response finished
- tool request started
- tool response finished
- subagent request started
- final response sent

## Why facts matter

Facts must stay stable even when:

- judges change
- prompts change
- ranking logic changes
- dataset builders evolve

This is how historical runs remain reusable.
```

---

## `docs/concepts/execution_graph.md`

```md
# Execution Graph

The execution graph is a derived structure built from immutable execution facts.

It organizes runtime behavior into reusable views such as:

- session view
- episode view
- branch tree
- replay timeline
- causality-aware execution graph

Facts are immutable.
Graphs are derived.

That distinction is fundamental to ClawGraph.
```

---

# 七、建议新增的 guides 页面内容

## `docs/guides/proxy_mode.md`

```md
# Proxy Mode

Proxy mode is the default adoption path for ClawGraph.

## What it gives you

- low-intrusion capture
- replay-ready fact collection
- branch inference v0
- dataset export capability

## What it does not guarantee

Proxy mode alone cannot always recover:

- planner boundaries
- explicit retry reasons
- controller route decisions
- stop vs continue semantics

When you need those, add the semantic contract.
```

---

## `docs/guides/semantic_mode.md`

```md
# Semantic Mode

Semantic mode builds on proxy mode.

Use it when you want higher-fidelity learning semantics from the runtime.

## Typical semantic signals

- plan_created
- subgoal_selected
- retry_declared
- branch_open_declared
- stop_decision_declared
- controller_route_decided

## When to use it

- process supervision
- planner/controller learning
- more accurate branch interpretation
- higher-quality sample building
```

---

## `docs/guides/replay_and_debug.md`

```md
# Replay and Debug

ClawGraph replay is not just playback.

It is designed to support learning-oriented analysis.

## What a good replay should show

- execution timeline
- branch tree
- retries and repairs
- artifact overlays
- ranking/chosen-rejected context
- dataset/export lineage

This is why ClawGraph replay is closer to a learning cockpit than a standard trace viewer.
```

---

## `docs/guides/export_to_echo.md`

```md
# Export to Echo

ClawGraph is designed to stay loosely coupled from downstream training systems.

## Intended boundary

- ClawGraph captures and structures execution
- Echo consumes exported datasets and supervision-derived samples

## Typical export families

- SFT samples
- preference pairs
- binary RL samples
- lineage-aware export records

Use the Echo bridge when you want ClawGraph to remain your capture and data organization layer, while Echo remains your training and serving backend.
```

---

# 八、建议新增的 reference 页面内容

## `docs/reference/builder_interface.md`

````md
# Builder Interface

A builder consumes graph views and artifact views and emits a dataset.

## Conceptual interface

```python
build(
    trajectory_view,
    artifact_view,
    memory_view=None,
    selection_query=None,
    context=None,
)
````

## Why builders matter

Builders are what make ClawGraph more than a capture system.

They are the abstraction that transforms reusable execution graphs into reusable learning data.

````

---

## `docs/reference/cli_reference.md`

```md
# CLI Reference

## `clawgraph proxy`
Start the proxy server.

### Example
```bash
clawgraph proxy \
  --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
````

## `clawgraph replay`

Inspect a captured session or episode.

### Example

```bash
clawgraph replay --session latest
```

## `clawgraph export dataset`

Export a dataset using a builder.

### Example

```bash
clawgraph export dataset \
  --builder preference \
  --session latest \
  --out ./exports/preference.jsonl
```

````

---

# 九、仓库初始化文件建议

## `pyproject.toml` 初稿

```toml
[project]
name = "clawgraph"
version = "0.1.0"
description = "Immutable, branch-aware execution graphs for OpenClaw-style agents"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn>=0.30.0",
  "pydantic>=2.8.0",
  "httpx>=0.27.0",
  "typer>=0.12.0",
  "sqlmodel>=0.0.22"
]

[project.scripts]
clawgraph = "clawgraph.cli.main:app"

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"
````

---

## `Makefile` 初稿

```make
.PHONY: install dev docs test lint

install:
	pip install -e .

dev:
	uvicorn clawgraph.proxy.server:app --reload --port 8080

docs:
	cd docs && npm run docs:dev

test:
	pytest

lint:
	python -m compileall clawgraph
```

---

## `.gitignore` 初稿

```gitignore
__pycache__/
*.pyc
.venv/
.env
dist/
build/
.pytest_cache/
docs/.vitepress/cache/
docs/.vitepress/dist/
clawgraph.db
```

---

# 十、首轮源码占位文件建议

为了让 vibe coding 更顺手，我建议先生成这些最小占位文件。

## `clawgraph/__init__.py`

```python
__all__ = []
```

## `clawgraph/cli/main.py`

```python
import typer

app = typer.Typer()

@app.callback()
def main():
    """ClawGraph CLI."""
    pass
```

## `clawgraph/proxy/server.py`

```python
from fastapi import FastAPI

app = FastAPI(title="ClawGraph Proxy")
```

## `clawgraph/protocol/fact_schema.py`

```python
from pydantic import BaseModel
from typing import Any

class ExecutionFact(BaseModel):
    fact_id: str
    fact_type: str
    session_id: str | None = None
    episode_id: str | None = None
    branch_id: str | None = None
    timestamp_ms: int
    payload: dict[str, Any] = {}
```

## `clawgraph/protocol/artifact_schema.py`

```python
from pydantic import BaseModel
from typing import Any

class Artifact(BaseModel):
    artifact_id: str
    artifact_type: str
    target_ref: str
    source_type: str
    created_at_ms: int
    payload: dict[str, Any] = {}
```

## `clawgraph/protocol/branch_schema.py`

```python
from pydantic import BaseModel

class Branch(BaseModel):
    branch_id: str
    episode_id: str
    parent_branch_id: str | None = None
    branch_type: str
    declared_or_inferred: str = "inferred"
    status: str = "open"
```

## `clawgraph/protocol/semantic_schema.py`

```python
from pydantic import BaseModel
from typing import Any

class SemanticEvent(BaseModel):
    semantic_id: str
    semantic_type: str
    target_ref: str | None = None
    source: str
    timestamp_ms: int
    payload: dict[str, Any] = {}
```

---

# 十一、首轮任务拆解（最适合交给 vibe coding）

## Task 1：协议层

生成：

* fact schema
* artifact schema
* branch schema
* semantic schema

## Task 2：最小 sqlite store

生成：

* fact append
* artifact append
* basic list/query

## Task 3：proxy skeleton

生成：

* model proxy endpoint
* tool proxy endpoint
* upstream forwarding
* fact emission

## Task 4：CLI skeleton

生成：

* `clawgraph proxy`
* `clawgraph replay`
* `clawgraph export`

## Task 5：replay v0

生成：

* session timeline
* simple branch listing

## Task 6：builder skeleton

生成：

* base builder
* selector object
* sft/preference/binary_rl placeholders

## Task 7：docs site

生成：

* VitePress site
* nav/sidebar
* markdown pages

---

# 十二、到这一步，项目已经具备的东西

现在你已经有了：

* 清晰的项目定位
* 改进后的命名与叙事
* 完整 docs 结构
* 首页与导航信息架构
* repo 目录设计
* 核心协议边界
* proxy + semantic contract 的 adoption ladder
* 首轮开发任务顺序

已经足够进入**真正的 vibe coding 开发**。

下一步最合适的是我直接继续输出：

## **第一批源码文件初稿**

包括：

* `fact_schema.py`
* `artifact_schema.py`
* `branch_schema.py`
* `semantic_schema.py`
* `cli/main.py`
* `proxy/server.py`

这样你就能直接开始建仓。

