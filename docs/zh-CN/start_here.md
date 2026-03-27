# 开始使用

如果你第一次使用 ClawGraph，先按“你现在要完成的任务”来选路径。

ClawGraph 最容易分三步理解：

- 先在本地验证一条完整闭环
- 再接入真实 runtime
- 最后把捕获到的 run 导出成训练数据

## 1. 先在本地验证一条闭环

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

跑完之后你会看到：

- 一条完整的 OpenClaw 风格 session，并且里面有一个 run
- 一条声明式 retry branch
- 可 inspect 的 artifact
- 一次导出预览

接下来：

- 想沿着一条连续路径继续做：看 [15 分钟路径](./fifteen_minute_path.md)
- 想直接照仓库里的可运行文件走：看 [Examples](./examples.md)

## 2. 接入真实 runtime

如果你已经有 OpenClaw 风格或 OpenAI-compatible runtime，默认先走 proxy 接入。

推荐顺序：

- 先把 model 和 tool endpoint 指到 `clawgraph proxy`
- 先让 ClawGraph 自动分配 `session_id / run_id / request_id`
- 先 inspect session，再决定要不要补稳定 header
- 只有当 replay grouping 或 branch fidelity 不够时，再补 semantic event

先看：

- [接入说明](./openclaw_integration.md)
- [流程总览](./workflow_overview.md)
- [Replay 与调试](./replay_and_debug.md)

对应的 runnable examples：

- [openclaw_proxy_minimal](../../examples/openclaw_proxy_minimal/README.md)
- [openclaw_python_helper](../../examples/openclaw_python_helper/README.md)
- [openclaw_openai_wrapper](../../examples/openclaw_openai_wrapper/README.md)

## 3. 导出训练数据

如果你已经有 captured runs，下一步就不是继续“接入”，而是先确认哪个 run 可导出。

推荐顺序：

- 先 inspect session，再用 `clawgraph list runs --session <id>` 选 run
- 没有 artifact 时，先跑默认 bootstrap
- 再看 `readiness`
- 最后 `export dataset` 或 `pipeline run`

先看：

- [数据导出](./dataset_builders.md)
- [CLI 参考](./cli_reference.md)
- [Examples](./examples.md)

## 记住这套作用域心智

- `session` 是容器
- `run` 是容器里一次执行回合
- inspect 和 replay 先按 session 看
- readiness、artifact bootstrap、pipeline、export 默认落在最新 run

## 想先看系统边界

如果你想先理解产品边界，再动手接入，可以补读英文版：

- [What is ClawGraph](../overview/what_is_clawgraph.md)
- [Architecture](../overview/architecture.md)
- [Why Not Tracing](../overview/why_not_tracing.md)
