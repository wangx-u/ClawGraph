# 设计标准：切片与 Cohort 策展

本文定义如何把“已有采集会话”筛选、分类、聚合成后续训练和评测可复用的 cohort。

这是这一版设计新增的核心层。

## 1. 为什么要单独成层

当前系统已经擅长：

- 采集和回放单个 session / run
- 对单个 run 做 artifact bootstrap
- 用 builder 导出某个 run 的训练记录

但这还不等于数据治理。

真正缺的中间层是：

- 如何从大量 session 中挑出同类任务
- 如何识别哪些只是模板近重复
- 如何把同一任务实例的多条 run 聚在一起
- 如何把低置信或新 subtype 打回 review queue
- 如何冻结一版候选集合供训练和评测复用

这层就是 cohort curation。

## 2. 一等对象

| 对象 | 含义 |
| --- | --- |
| `slice` | 一个稳定、可命名、可评测的任务切片 |
| `candidate pool` | 满足基础条件、可能属于某个 slice 的记录集合 |
| `cluster` | 近重复、同模板、同路径或同失败模式的聚类 |
| `cohort` | 经审核后冻结的一批样本来源 |
| `review queue` | 低置信分类、新 subtype、异常 case 的待审池 |
| `holdout feed` | 明确保留给评测、暂不进入训练的候选流 |

从产品上看，`cohort` 是 builder 之前最重要的边界对象。

## 3. 标准流程

```text
session inbox
  -> normalization
  -> auto classification
  -> quality gate
  -> dedupe and clustering
  -> slice assignment
  -> review queue for low-confidence or new subtype
  -> cohort freeze
  -> dataset snapshot or eval suite
```

## 4. Session Inbox 标准

进入 session inbox 的记录，至少应具备：

- 可回放的 request / response / error
- 基本 identity 信息
- 至少能归因到某个 `run`

session inbox 的职责不是直接导出，而是先判断：

- 这批记录属于什么 slice
- 是否需要补标
- 是否应该进训练、评测还是只做诊断

## 5. Slice Registry 标准

`slice` 必须来自 registry，而不是临时筛选条件。

每个 slice 至少要记录：

- `slice_id`
- `task_family`
- `task_type`
- taxonomy 版本
- 推荐 sample unit
- 期望 verifier 契约
- 风险级别
- 默认用途
- owner

默认用途至少区分：

- `training_candidate`
- `eval_only`
- `diagnostics_only`

没有 registry 的临时自由筛选，不应直接变成长期 cohort。

## 6. Candidate Pool 标准

每个 slice 的 candidate pool 必须是显式查询结果，而不是训练脚本里的隐式逻辑。

基础筛选维度应包括：

- `task_family`
- `task_type`
- `task_instance_key`
- `task_template_hash`
- `teacher_model`
- `policy_version`
- `difficulty`
- `verifier_score`
- `quality_confidence`
- `source_channel`
- 时间窗口

默认排除：

- open span
- 无法解析 prompt / response 的记录
- taxonomy 未知且置信度不足的记录
- 外部系统故障主导的噪声记录

## 7. 聚类与聚合标准

cohort 不是“把所有符合条件的 run 全塞进去”。

默认需要三类聚类：

### 模板聚类

按 `task_template_hash` 聚合，防止同模板轻微改写充斥 cohort。

### 任务实例聚类

按 `task_instance_key` 聚合，确保同一个真实任务实例不会被拆散处理。

### 路径或失败模式聚类

按工具路径骨架、终局输出结构、失败模式聚类，避免 cohort 只反映一种成功路径。

聚类后的 cohort 应按配额抽样，而不是按原始量级直接吞下。

## 8. 低置信与新 subtype 处理

以下记录必须进入 review queue，而不是自动进 training cohort：

- `unknown` 或 `new_subtype`
- `quality_confidence` 低于阈值
- verifier 与人工判断长期冲突
- 同一 `task_instance_key` 下出现异常多条互相矛盾的轨迹
- 新工具路径或新失败模式

review queue 的处理结果必须可回写为新的 artifact 或 taxonomy 版本，而不是停留在人工备注。

## 9. Cohort 冻结标准

一个 cohort 只有满足以下条件才可冻结：

1. 绑定到明确的 `slice_id` 或 slice 集合。
2. 过滤条件、时间范围和排除规则明确。
3. 去重和近重复聚类已执行。
4. review queue 已处理到可接受水平。
5. 记录知道将流向 `training`、`evaluation` 还是 `diagnostics`。

cohort 冻结后，默认应生成 manifest，至少包含：

- `cohort_id`
- slice 范围
- taxonomy 版本
- 时间范围
- session / run 数量
- cluster 统计
- 排除原因统计
- review 决策统计
- 预期下游用途

## 10. 产品形态建议

如果从展示和产品形态看，这一层应优先长成四个界面：

### Session Inbox

看新采集会话，识别缺失 annotation、异常路径和新 subtype。

### Slice Builder

按 taxonomy、时间窗口、teacher、difficulty、verifier 建 candidate pool。

### Cohort Review

看 cluster、抽样、排除原因和 review queue，决定是否冻结。

### Holdout Feed

把更晚时间窗口、新 subtype、高风险 case 明确保留给评测，不混进训练。

## 11. 当前版本的设计结论

- “已有采集会话如何变成训练和测试集”不能直接靠 builder 解决，必须先经过 cohort curation。
- cohort 是 session/run 和 dataset snapshot 之间的新一等边界对象。
- taxonomy、cluster、review queue、holdout feed 都应在这一层定义，而不是散落在训练脚本或评测脚本里。
