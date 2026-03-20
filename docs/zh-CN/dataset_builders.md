# 数据导出

ClawGraph 的导出流程分两步：

1. 先确认 session 是否具备导出条件
2. 再按 builder 导出训练数据

## 先看 readiness

```bash
clawgraph readiness --session latest --builder sft
clawgraph readiness --session latest --builder preference
clawgraph readiness --session latest --builder binary_rl
```

`readiness` 会告诉你：

- 是否可导出
- 缺什么条件
- 预计会产出多少条记录

## 常见 builder

### SFT

适合先把真实运行里的高质量 assistant 响应变成监督数据。

```bash
clawgraph export dataset --builder sft --session latest --dry-run
clawgraph export dataset --builder sft --session latest --out out/sft.jsonl
```

### Preference

适合已有 retry、fallback 或显式 ranking / preference artifact 的场景。

```bash
clawgraph export dataset --builder preference --session latest --dry-run
clawgraph export dataset --builder preference --session latest --out out/preference.jsonl
```

### Binary RL

适合已经有 score / reward / label artifact 的场景。

```bash
clawgraph export dataset --builder binary_rl --session latest --dry-run
clawgraph export dataset --builder binary_rl --session latest --out out/binary_rl.jsonl
```

## 如果还没有 artifact

可以先用默认模板补一轮 supervision：

```bash
clawgraph artifact bootstrap --template openclaw-defaults --session latest
```

这通常会先生成：

- request outcome score
- branch outcome preference

然后再重新检查 readiness。

## 导出前建议先 inspect

```bash
clawgraph inspect session --session latest
clawgraph replay --session latest
clawgraph list requests --session latest
```

先确认轨迹质量，再导出训练数据，通常比直接批量导出更稳。

## 下一步

- 想看一条连续路径：
  看 [15 分钟路径](./fifteen_minute_path.md)
- 想接真实 runtime：
  看 [接入说明](./openclaw_integration.md)
- 想看更完整的英文 builder 说明：
  看 [Dataset Builders](../guides/dataset_builders.md)
