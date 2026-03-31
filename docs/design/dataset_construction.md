# 设计标准：数据集快照与切分治理

本文定义怎样把已经冻结的 cohort 构造成可复现的 `train / val / test` 数据集快照。

这里讨论的是 dataset governance，不是 evidence capture，也不是上线评测。

## 1. 核心边界

从这版设计开始，dataset builder 的输入不应再被理解为“某个最新 run”。

builder 的规范输入应该是：

- 一个冻结的 cohort
- 一个明确的 dataset recipe
- 一个明确的 sample unit

因此，builder 的职责是：

- 把 cohort 变成训练记录
- 固化 split assignment
- 输出 manifest

builder 不负责：

- 决定哪些 session 应该进入候选池
- 管理 taxonomy
- 管理 golden / shadow / canary 评测资产

## 2. 一等对象

| 对象 | 含义 |
| --- | --- |
| `dataset recipe` | 某个 builder 家族的构建规则版本 |
| `dataset snapshot` | 某一版冻结后的 `train / val / test` 数据集 |
| `split assignment` | 某个样本归属到哪个 split 的固定决定 |
| `sample unit` | 训练记录的基础单位，必须是 `request`、`branch` 或 `run` |

`dataset snapshot` 一旦冻结，就应被训练、评测和回归材料按版本引用。

## 3. 标准流程

```text
frozen cohort
  -> sample-unit normalization
  -> family-specific record construction
  -> pair / reward resolution
  -> dedupe and leakage guard
  -> split assignment
  -> weighting
  -> manifest
  -> dataset snapshot
```

## 4. sample unit 标准

禁止把任意连续对话 turn 直接当成训练样本。

允许的基础单位只有：

| 单位 | 典型用途 |
| --- | --- |
| `request` | SFT、局部 reward、工具调用正确性 |
| `branch` | preference、路径选择、修复策略学习 |
| `run` | episode 级 binary RL、route outcome、完成率 |

一个 dataset recipe 必须在 manifest 中显式写清其 sample unit。

## 5. 三类训练样本标准

### SFT

`SFT` 样本应满足：

- request 已闭合
- prompt 与 completion 可解析
- completion 是期望教师目标，而不是未筛选的中间失败轨迹
- `quality_confidence` 达到阈值
- 所属 slice 和 `task_instance_key` 已知

### Preference

`preference` 样本应满足：

- chosen 与 rejected 属于同一 `task_instance_key`
- 比较双方处于同一 slice，且比较口径一致
- 比较理由可追溯到 artifact、verifier 或 branch outcome
- 不允许跨任务实例强行配对

默认优先在 branch 内或同任务实例下生成 pair，而不是跨 session 随机凑 pair。

### Binary RL

`binary RL` 样本应满足：

- reward target 明确绑定到 `request`、`branch` 或 `run`
- reward 是数值型，且来自稳定验证逻辑
- reward 的 producer、version、confidence 可追溯
- 失败样本可以进入，但必须能解释失败来自什么 verifier 口径

没有 verifier 的开放式主观偏好，默认不进入 binary RL。

## 6. 去重与泄漏控制

默认必须执行两级控制：

### 精确去重

按以下信息计算 canonical hash：

- 规范化 prompt
- `task_type`
- `task_instance_key`
- 工具轨迹骨架
- terminal output 或 completion

完全相同的记录只保留一份。

### 近重复聚类

对于同模板轻微改写、同工具路径、同输出结构的记录，必须做聚类抽样。

至少应支持以下 cluster key：

- `task_template_hash`
- 工具路径骨架
- 终局输出结构
- 失败模式

否则训练和测试都会系统性高估效果。

## 7. split 标准

训练 split 只包含：

- `train`
- `val`
- `test`

`golden` 和 `shadow` 不是训练 split，而是评测资产，必须放到评测文档单独治理。

默认 split 规则：

1. 先按 `slice_id` 或等价的 `task_family / task_type` 分层。
2. 再按 `task_instance_key` 保证同任务实例不跨 split。
3. 再按 `session_id / run_id` 保证同 episode 不跨 split。
4. 在可行时，再按时间做更晚窗口的 `test` 留出。

默认禁止：

- 按 response 随机切分
- 按单 turn 随机切分
- 训练时回流 `test`

如果 `task_instance_key` 缺失，则必须在 manifest 里声明退化到什么 leakage guard。

## 8. 权重标准

默认权重应综合考虑：

- `quality_confidence`
- `verifier_score`
- `difficulty`
- `task_family` 稀缺度
- `teacher_model` 混合比例
- cluster 内抽样密度

禁止让“数量最多但价值最低”的 easy slice 主导训练。

## 9. Manifest 标准

每个 dataset snapshot 除样本本身外，必须附带 manifest，至少包含：

- `dataset_snapshot_id`
- `dataset_recipe_id`
- builder 名称与版本
- sample unit
- 对应 `cohort_id`
- taxonomy 版本
- 时间范围
- 源 `session_id` / `run_id` 统计
- `task_family` / `task_type` 分布
- `teacher_model` 分布
- `difficulty` 分布
- verifier / reward 来源
- 去重规则版本
- split 规则版本
- 泄漏防护 key

manifest 的目标不是“补充说明”，而是让 dataset snapshot 可复现、可审计。

## 10. 数据集 readiness 标准

一个 dataset snapshot 只有同时满足以下条件才算 ready：

1. 构建输入来自冻结 cohort，而不是隐式查询。
2. sample unit 清晰，builder 能稳定复现。
3. 任务切片分布已知。
4. 去重和近重复聚类已执行。
5. `train / val / test` 无明显泄漏。
6. verifier 或 preference 来源清晰。
7. manifest 可追溯回 cohort、facts 和 artifacts。

## 11. 当前版本的设计结论

- builder 前面必须增加 cohort 这一层，不能继续把 run 直接等价成 dataset source。
- `train / val / test` 是 dataset snapshot 的边界；`golden / shadow` 从这里移出。
- dataset builder 的职责是冻结和导出自包含训练记录，不负责替代上游的数据治理。
