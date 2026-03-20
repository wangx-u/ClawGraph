# 开始使用

如果你第一次使用 ClawGraph，先走最短路径。

## 最快跑通一遍

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

- 一条完整的 OpenClaw 风格 session
- 一条声明式 retry branch
- 可 inspect 的 artifact
- 一次导出预览

## 你接下来该去哪

### 我想沿着一条完整路径继续做

看 [15 分钟路径](./fifteen_minute_path.md)

### 我已经有 runtime，想接真实流量

看英文版 [OpenClaw Integration](../guides/openclaw_integration.md)

### 我想先理解系统边界

看英文版：

- [What is ClawGraph](../overview/what_is_clawgraph.md)
- [Architecture](../overview/architecture.md)
- [Why Not Tracing](../overview/why_not_tracing.md)

### 我想看 examples

看英文版 [Examples](../guides/examples.md)
