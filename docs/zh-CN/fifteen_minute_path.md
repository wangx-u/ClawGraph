# 15 分钟上手路径

这份文档把首跑、接入和导出串成一条连续路径。

## 第一步：先在本地验证闭环

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

详细接入说明看英文版 [OpenClaw Integration](../guides/openclaw_integration.md)。

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

## 接下来该看什么

- 如果你主要关心 replay 和调试：
  看英文版 [Replay and Debug](../guides/replay_and_debug.md)
- 如果你主要关心 builder 和导出：
  看英文版 [Dataset Builders](../guides/dataset_builders.md)
- 如果你要接到异步训练：
  看英文版 [Export to Async RL](../guides/export_to_async_rl.md)
