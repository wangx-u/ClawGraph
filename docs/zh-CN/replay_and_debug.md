# Replay 与调试

当你需要先回答“运行时到底发生了什么”，再决定能不能导出训练数据时，用这页。

ClawGraph 的 replay 不是纯运维 trace 视图，而是面向学习和导出的排查入口。

## 最小排查路径

```bash
clawgraph inspect session --session latest
clawgraph list runs --session latest
clawgraph list requests --session latest
clawgraph inspect request --session latest --request-id latest
clawgraph replay --session latest
clawgraph inspect branch --session latest
clawgraph readiness --session latest --builder preference
clawgraph export dataset --builder preference --session latest --dry-run
```

推荐顺序：

1. 先确认这次 capture 落到了哪个 session
2. 再用 request 视图找到失败、变慢或异常的那一步
3. 用 replay 看时间线、branch 结构和 retry / fallback
4. inspect branch，确认 inferred branch 和 declared branch 是否一致
5. 只有 replay 看起来正确，再做 readiness 或 export dry-run

## Replay 里最值得看什么

- 执行时间线
- branch 树
- retry / repair / fallback
- 挂载的 artifact
- readiness 或 export 之前的上下文完整性

## 什么时候该补更多结构

- session 或 run 很难关联时：补稳定 header
- retry / fallback 推断不准时：补 semantic event
- 轨迹是对的但 supervision 不够时：补 artifact 或先跑 bootstrap

## 常用配套命令

- `clawgraph inspect session`
- `clawgraph inspect request`
- `clawgraph inspect branch`
- `clawgraph readiness --builder <builder>`
- `clawgraph export dataset --builder <builder> --dry-run`

## 下一步

- 想接真实 runtime：看 [接入说明](./openclaw_integration.md)
- 想走完整流程：看 [15 分钟路径](./fifteen_minute_path.md)
- 想导出训练数据：看 [数据导出](./dataset_builders.md)
- 想查 CLI 细节：看 [CLI 参考](./cli_reference.md)
