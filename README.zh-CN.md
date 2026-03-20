# ClawGraph

<p align="center">
  <img src="docs/clawgraph-logo.png" alt="ClawGraph logo" width="160">
</p>

### 面向 OpenClaw 风格 Agent 的不可变、分支感知执行图

ClawGraph 用来把真实 agent 运行过程变成可复用的学习数据：先捕获，
后监督，再导出到 SFT、preference、binary RL、async RL 和 distillation。

> 大多数 tracing 系统是为监控而设计。ClawGraph 是为学习而设计。

[English](README.md) | [简体中文](README.zh-CN.md)

## 为什么团队会用它

- 已有 runtime 也能接入，先走 proxy，不要求重写 agent
- 一次采集，同时支持 replay、inspect、readiness 和 export
- 原生支持 retry、fallback、subagent 这类分支结构
- 对 streaming、tool call 和 downstream export 提供更稳定的 canonical 输出

## 5 分钟上手

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

后续接真实 runtime：

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

## 按目标开始

| 目标 | 文档 |
| --- | --- |
| 最快跑通一遍 | [`docs/zh-CN/start_here.md`](docs/zh-CN/start_here.md) |
| 从首跑一路到导出 | [`docs/zh-CN/fifteen_minute_path.md`](docs/zh-CN/fifteen_minute_path.md) |
| 接入 OpenClaw / OpenAI-compatible runtime | [`docs/zh-CN/openclaw_integration.md`](docs/zh-CN/openclaw_integration.md) |
| 看 replay、branch、readiness | [`docs/guides/replay_and_debug.md`](docs/guides/replay_and_debug.md) |
| 看导出和训练数据 | [`docs/zh-CN/dataset_builders.md`](docs/zh-CN/dataset_builders.md) |

## 常用命令

- `clawgraph bootstrap`
- `clawgraph proxy`
- `clawgraph list readiness`
- `clawgraph replay`
- `clawgraph inspect`
- `clawgraph pipeline run`
- `clawgraph readiness`
- `clawgraph export dataset`

## 文档

- 中文入口: [`docs/zh-CN/README.md`](docs/zh-CN/README.md)
- 中文 Start Here: [`docs/zh-CN/start_here.md`](docs/zh-CN/start_here.md)
- 中文 15 分钟路径: [`docs/zh-CN/fifteen_minute_path.md`](docs/zh-CN/fifteen_minute_path.md)
- 中文接入说明: [`docs/zh-CN/openclaw_integration.md`](docs/zh-CN/openclaw_integration.md)
- 中文流程总览: [`docs/zh-CN/workflow_overview.md`](docs/zh-CN/workflow_overview.md)
- 中文数据导出: [`docs/zh-CN/dataset_builders.md`](docs/zh-CN/dataset_builders.md)
- 英文 docs 首页: [`docs/index.md`](docs/index.md)
- Examples: [`examples/README.md`](examples/README.md)
- CLI Reference: [`docs/reference/cli_reference.md`](docs/reference/cli_reference.md)

ClawGraph 是一个面向学习的执行数据底座，不是新的 agent runtime，
不是 trainer，也不绑定单一 RL 算法。

## 项目文件

- 路线图: [`ROADMAP.md`](ROADMAP.md)
- Backlog: [`BACKLOG.md`](BACKLOG.md)
- 贡献说明: [`CONTRIBUTING.md`](CONTRIBUTING.md)
