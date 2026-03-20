# 接入 OpenClaw 风格 Runtime

如果你已经有 OpenClaw 或兼容 OpenAI API 的 runtime，推荐先走 proxy 接入。

## 最小接入方式

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

把 runtime 的模型请求和工具请求改为经过 ClawGraph 代理后，你就能得到：

- 不可变的 execution facts
- session / request / branch inspect
- replay 和 readiness
- 后续可追加的 artifact 和 dataset export

## 建议补的请求头

如果 runtime 能带上这些 header，后续 inspect 和 export 会更稳：

- `x-clawgraph-session-id`
- `x-clawgraph-run-id`
- `x-clawgraph-request-id`
- `x-clawgraph-user-id`

## 什么时候补 semantic event

只靠 proxy 时，ClawGraph 已经能推断一部分 retry / branch 信息。  
如果你希望更高保真的 branch 语义，再补 semantic event：

- `retry_declared`
- `fallback_declared`
- `route_decided`
- `subagent_spawned`

## 接入后先做什么

推荐顺序：

1. `clawgraph inspect session --session latest`
2. `clawgraph list requests --session latest`
3. `clawgraph replay --session latest`
4. `clawgraph readiness --session latest --builder sft`

如果还没有 supervision，可以先跑：

```bash
clawgraph artifact bootstrap --template openclaw-defaults --session latest
```

然后再检查：

```bash
clawgraph readiness --session latest --builder preference
clawgraph export dataset --builder preference --session latest --dry-run
```

## 下一步

- 想看完整从首跑到导出的路径：
  看 [15 分钟路径](./fifteen_minute_path.md)
- 想看更细的英文接入文档：
  看 [OpenClaw Integration](../guides/openclaw_integration.md)
- 想看导出和 builder：
  看 [数据导出](./dataset_builders.md)
