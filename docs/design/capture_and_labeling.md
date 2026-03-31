# 设计标准：证据采集与标注

本文定义 ClawGraph 如何把 proxy capture 变成“可治理的证据层”。

这里不直接讨论训练集导出，而是规定后续 cohort、dataset、evaluation 能否成立的前置条件。

## 1. 核心原则

ClawGraph 的原始 proxy 数据只能作为证据层，不能直接当训练样本。

原因不是“proxy 数据没用”，而是它只回答了低层执行事实：

- 谁发起了请求
- 请求和响应长什么样
- 工具有没有返回
- 时延和错误码是什么

它默认不回答：

- 这个请求属于什么业务任务
- 同一个会话里的哪些请求其实属于同一 task instance
- 这次 retry / fallback / repair 为什么发生
- 哪个输出值得作为教师目标
- 哪个失败样本应该进训练，哪个只应该进评测或诊断

因此，训练前必须先补 annotation，而不是把事实层直接喂给 builder。

## 2. 分层对象模型

ClawGraph 在 evidence layer 使用两类对象：

| 对象 | 含义 | 是否可变 |
| --- | --- | --- |
| `fact` | append-only 的执行事实 | 否 |
| `artifact` / `semantic event` | 对事实的外挂标注、评分、分类或解释 | 是，需版本化 |

事实层对象的身份模型仍然是：

| 对象 | 说明 |
| --- | --- |
| `session` | 长生命周期容器，适合 inspect 和归档 |
| `run` | 一次执行 episode，是当前导出和回放的最小闭环 |
| `request` | 一次模型、工具或 runtime 请求 |
| `branch` | run 内的一条可比较路径 |

但从这版设计开始，还必须显式补一个治理层 key：

| key | 层级 | 作用 |
| --- | --- | --- |
| `task_instance_key` | artifact | 用来表达“这几条执行记录其实在解决同一个任务实例” |

`run` 是执行边界，`task_instance_key` 是策展和防泄漏边界。

如果没有 `task_instance_key`，就无法稳定地：

- 生成高质量 preference pair
- 阻断同任务实例跨 split 泄漏
- 把多条相关 run 聚成一个 cohort

## 3. 采集层最低要求

以下字段必须能在 facts 或可追溯 artifact 中恢复：

| 字段 | 层级 | 说明 |
| --- | --- | --- |
| `session_id` | session | 长生命周期容器 |
| `run_id` | run | 一次执行 episode |
| `request_id` | request | 单请求唯一标识 |
| `parent_ref` | request / branch | 父请求或父分支 |
| `branch_id` | branch | 分支归属 |
| `user_id` / `thread_id` / `task_id` | context | 用户、线程、业务归因 |
| `actor` / `kind` / `timestamp` | fact | 行为类型和时序 |
| request prompt | request | 训练输入基础材料 |
| response or error | request | 输出或失败原因 |
| tool call inputs / outputs | request | 工具依赖分析 |
| latency / status code | request | 成功率、代价、SLA 分析 |
| producer / policy version / model name | artifact | 教师来源与策略来源 |
| source channel | artifact | 流量来源，如 prod、shadow、rerun |

如果这些字段无法恢复，数据最多用于 replay，不应进入后续策展。

## 4. 必须补充的标注字段

在进入 cohort curation 之前，至少应补齐以下 annotation：

| 字段 | 目标层级 | 作用 |
| --- | --- | --- |
| `task_family` | request / run | 粗粒度切片主键 |
| `task_type` | request / run | 细粒度切片主键 |
| `task_template_hash` | request / run | 模板聚类和泄漏控制 |
| `task_instance_key` | run / branch / request | 同一任务实例聚合、防泄漏、防错配 |
| `difficulty` | request / run | 难度分层与采样权重 |
| `risk_tier` | run | 高风险任务保护和放量约束 |
| `verifier_name` | request / branch / run | 验证器来源 |
| `verifier_score` | request / branch / run | 自动验收分数 |
| `quality_confidence` | artifact | 标签可信度 |
| `tool_count` | request / branch / run | 工具复杂度 |
| `tool_success_rate` | branch / run | 工具闭环成功率 |
| `context_tokens` | request / run | 上下文压力 |
| `response_tokens` | request | 输出成本 |
| `teacher_model` | request / branch / run | 教师来源 |
| `policy_version` | request / branch / run | 策略或路由版本 |
| `annotation_version` | artifact | 标注规则版本 |
| `source_channel` | run | 来自 prod、shadow、judge rerun 还是人工回灌 |

这些字段应优先通过 artifact 追加，而不是改写原始 facts。

## 5. taxonomy 与未知类型处理

`task_family` 和 `task_type` 不是临时字符串，而应受 taxonomy 管理。

默认要求：

1. taxonomy 必须带版本。
2. `unknown` 和 `new_subtype` 必须保留显式值，不能静默塞进已有类型。
3. 低置信分类必须进入 review queue，而不是直接进入训练 cohort。
4. 任何切片分析、评测、放量结论都必须记录所使用的 taxonomy 版本。

如果 taxonomy 不稳定，后续 dataset 和 scorecard 就不再可比。

## 6. 必须补充的语义事件

对于 agent 级任务，下面这些事件属于默认目标：

| 事件 | 目标 | 用途 |
| --- | --- | --- |
| `task_opened` | run | 显式声明任务开始或任务实例切换 |
| `route_decided` | run / request | 记录走了哪个模型或策略 |
| `retry_declared` | branch / request | 记录 retry 原因 |
| `fallback_declared` | branch / request | 记录 fallback 原因 |
| `branch_opened` | branch | 记录新分支产生原因 |
| `task_completed` | run | 记录 episode 终止条件 |
| `verifier_completed` | request / branch / run | 记录自动验收结果 |
| `human_review_requested` | request / run | 记录进入人工审查的原因 |

如果某个切片没有这些语义事件，则：

- 可以进入 replay 和诊断
- 可以进入受限的 SFT 候选
- 不应直接进入 branch preference、run 级 RL 或线上替代判定

## 7. 标注来源与置信度

所有 annotation 都必须声明来源。

最少要区分：

- rule-based classifier
- verifier / judge
- human review
- imported external label

并且必须附带：

- `annotation_version`
- `quality_confidence`
- `producer`
- `created_at`

没有 provenance 的“裸标签”，不能作为训练和评测口径。

## 8. 证据层 readiness 等级

按后续可用性把 evidence 分成三层：

### E0：Replay-ready

只有 request/response/error capture。

适用：

- replay
- inspect
- 故障排查

不适用：

- 自动聚成 cohort
- 高质量数据切分
- 替代验证

### E1：Curation-ready

在 E0 基础上补齐 task、template、instance、verifier、quality 等 annotation。

适用：

- candidate pool 构建
- slice 归类
- 多会话聚合
- 训练候选筛选

### E2：Decision-ready

在 E1 基础上补 route、retry、fallback、completion 等语义事件，并能解释标签来源。

适用：

- 高质量 preference / binary RL
- slice coverage 判定
- offline / shadow / canary 替代验证

## 9. Builder 前质量门槛

一个样本进入 cohort curation 或 builder 前必须满足：

1. 请求是闭合的，不能是 open span。
2. prompt、response、error 至少一类可解析。
3. 能定位其 `request`、`branch`、`run` 归属。
4. 至少能分类到 `task_family`，理想情况下要到 `task_type`。
5. 至少能恢复 `task_instance_key` 或等价防泄漏 key。
6. 标签来源和版本可追溯。
7. 如果要进入 RL 或替代验证，必须存在稳定 verifier。

## 10. 当前版本的设计结论

- 证据层的核心职责是“保真和可追溯”，不是“直接导出训练集”。
- `task_instance_key`、taxonomy version、annotation provenance 是这一版必须新增的一等字段。
- 没有到 E1 的数据，不应进入 cohort；没有到 E2 的数据，不应进入替代验证和放量判定。
