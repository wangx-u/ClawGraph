# 流程总览

现在的 ClawGraph 可以分成 3 条实际可用的流程。

这页用来回答一个问题：
你到底应该走“零配置接入”、“半自动流水线”，还是“完全手动控制”。

## 1. 零配置 runtime 接入

适合：

- 已有 OpenClaw 风格 runtime
- 想快速接生产流量
- 想先看到信号，再决定要不要改 runtime

默认路径：

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db

clawgraph inspect session --session latest
clawgraph replay --session latest
clawgraph pipeline run --session latest --builder preference --dry-run
```

这一层自动完成：

- proxy capture
- 自动生成 `session_id / run_id / request_id`
- 对浏览器风格客户端自动复用 session 和当前 run
- replay 和 inspect
- 对最新捕获 run 做 pipeline 预览

这一层仍然是可选增强：

- 通过 header 提供稳定 id
- semantic event
- 自定义 artifact

推荐心智模型：

- `session` 是先拿来定位和排查的容器
- `run` 是容器里一次执行回合
- inspect 和 replay 默认先看整个 session
- readiness、artifact bootstrap、pipeline、export 默认落在最新 run

## 2. 半自动流水线

适合：

- RL 工程师
- 评测团队
- 要做 export gate 的平台团队

默认路径：

```bash
clawgraph list readiness --builder preference
clawgraph pipeline run --session latest --builder preference --dry-run
clawgraph pipeline run --session latest --builder preference --out out/preference.jsonl
```

这一层自动完成：

- 内置 supervision bootstrap
- builder-specific readiness
- 数据导出和 manifest
- `clawgraph list readiness` 会按最近 run 扫描

仍然需要人工决定：

- 用哪个 builder
- 导出哪个 scope
- 什么时候正式落库和导出

## 3. 完全手动控制

适合：

- evaluator 重打分
- 手工写 artifact
- 需要精确控制 supervision 的研究流程

典型路径：

```bash
clawgraph replay --session latest
clawgraph artifact bootstrap --template request-outcome-scores --session latest --dry-run
clawgraph artifact append --type score --target-ref latest-model-response --producer team.judge --payload '{"score": 1.0}'
clawgraph artifact list --session latest --latest-only
clawgraph readiness --session latest --builder binary_rl
clawgraph export dataset --builder binary_rl --session latest --out out/binary_rl.jsonl
```

这条路径更慢，但每一步都最可控。

## 推荐默认顺序

对大多数团队，建议顺序是：

1. 先走零配置 runtime 接入
2. 再走半自动流水线
3. 只有模板不够时，再下沉到完全手动控制

## 相关文档

- [接入说明](./openclaw_integration.md)
- [15 分钟路径](./fifteen_minute_path.md)
- [数据导出](./dataset_builders.md)
- [Replay 与调试](./replay_and_debug.md)
- [CLI 参考](./cli_reference.md)
