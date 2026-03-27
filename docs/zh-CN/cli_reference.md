# CLI 参考

这页只覆盖最常用、最容易混淆的命令和作用域。

完整英文参考仍在 [CLI Reference](../reference/cli_reference.md)。

## 先记住作用域

- `session` 是容器
- `run` 是这个容器里的一次执行回合
- inspect 和 replay 默认先看整个 session
- readiness、artifact bootstrap、pipeline、export 默认落在最新 run
- 一个 session 里有多个 run 时，用 `clawgraph list runs --session <id>` 先选 run

## 最常用的查看命令

```bash
clawgraph list sessions
clawgraph list runs --session latest
clawgraph list requests --session latest
clawgraph inspect session --session latest
clawgraph inspect request --session latest --request-id latest
clawgraph inspect branch --session latest
clawgraph replay --session latest
```

适用场景：

- `list sessions` / `list runs`: 先找你要看的 capture 范围
- `list requests`: 快速看这个 session 里有哪些请求
- `inspect session` / `inspect request` / `inspect branch`: 深入看单个对象
- `replay`: 先看轨迹和 branch 结构，再决定是否可导出

## 最常用的导出前命令

```bash
clawgraph artifact bootstrap --template openclaw-defaults --session latest --dry-run
clawgraph artifact bootstrap --template openclaw-defaults --session latest

clawgraph readiness --session latest --builder preference
clawgraph export dataset --builder preference --session latest --dry-run
clawgraph pipeline run --session latest --builder preference --dry-run
```

适用场景：

- `artifact bootstrap`: facts 有了，但还缺默认 supervision
- `readiness`: 看当前 run 对某个 builder 是否 ready
- `export dataset --dry-run`: 看记录数、blocker 和 manifest 预览
- `pipeline run`: 用一条命令串起 bootstrap、readiness、export gate

## `artifact append` 最常用 target shortcut

- `latest-response`
- `latest-failed-branch`
- `latest-succeeded-branch`
- `run:latest`
- `session:latest`

建议：

- 优先用 `run:latest` 做 run 级 supervision 和导出相关 target
- 只有你明确想挂 session 级 artifact 时，才用 `session:latest`

## 平台视角最常用的命令

```bash
clawgraph list readiness --builder preference
clawgraph artifact list --session latest --latest-only
```

适用场景：

- `list readiness`: 从最近 run 的视角看哪些已经可导出
- `artifact list --latest-only`: 看当前生效的 artifact

## 下一步

- 想看完整路径：看 [15 分钟路径](./fifteen_minute_path.md)
- 想看 replay 排查：看 [Replay 与调试](./replay_and_debug.md)
- 想看 runnable example：看 [Examples](./examples.md)
