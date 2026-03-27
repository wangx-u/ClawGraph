# 15 分钟上手路径

这份文档把首跑、接入和导出串成一条连续路径。

## 第一步：先在本地验证闭环

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

clawgraph bootstrap openclaw --store sqlite:///clawgraph.db
clawgraph inspect session --session latest
clawgraph list runs --session latest
clawgraph replay --session latest
clawgraph readiness --session latest --builder preference
clawgraph export dataset --builder preference --session latest --dry-run
```

## 第二步：接入真实 OpenClaw 风格 runtime

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

然后在 runtime 里逐步补这些 header：

- `x-clawgraph-session-id`
- `x-clawgraph-run-id`
- `x-clawgraph-request-id`
- `x-clawgraph-user-id`

如果需要更高保真的 branch 语义，再补 semantic event。

详细接入说明看 [接入说明](./openclaw_integration.md)。

术语上先记住一件事：

- `session` 是容器
- `run` 是这个容器里的一次执行回合
- inspect 和 replay 默认先看整个 session
- readiness 和 export 默认落在最新 run，除非你显式传 `--run-id`

## 第三步：把真实流量变成训练数据

对刚采集到但还没有 artifact 的 session：

```bash
clawgraph artifact bootstrap --template openclaw-defaults --session latest --dry-run
clawgraph artifact bootstrap --template openclaw-defaults --session latest
```

然后检查 readiness 并导出：

```bash
clawgraph readiness --session latest --builder sft
clawgraph readiness --session latest --builder preference
clawgraph readiness --session latest --builder binary_rl

clawgraph export dataset --builder preference --session latest --dry-run
clawgraph export dataset --builder preference --session latest --out out/preference.jsonl
```

如果你想把“补监督 + 看 readiness + 导出”收成一条正式流程，可以直接用：

```bash
clawgraph pipeline run --session latest --builder preference --dry-run
clawgraph pipeline run --session latest --builder preference --out out/preference.jsonl
```

如果你想先从平台视角看最近哪些 run 已经可导出，可以用：

```bash
clawgraph list readiness --builder preference
```

## 接下来该看什么

- 如果你主要关心 replay 和调试：
  看 [Replay 与调试](./replay_and_debug.md)
- 如果你主要关心 builder 和导出：
  看 [数据导出](./dataset_builders.md)
- 如果你要接到异步训练：
  先看 [CLI 参考](./cli_reference.md)，再补读英文版 [Export to Async RL](../guides/export_to_async_rl.md)
- 如果你想直接复制仓库里的 runnable example：
  看 [Examples](./examples.md)
