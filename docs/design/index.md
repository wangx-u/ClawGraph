# 设计总览：从 Proxy 证据到训练、评测与放量

这组文档定义 ClawGraph 在学习数据链路中的分层边界。

它要回答五个问题：

- proxy 保存的原始会话，怎样变成可治理的证据层
- 已有采集会话，怎样按任务切片筛选、分类、聚合成 cohort
- cohort 怎样冻结成 `train / val / test` 数据集快照
- 什么任务切片适合什么训练配方、模型带宽和线上覆盖策略
- 怎样把评测、放量、回流做成可审计闭环

这组文档是产品形态和后续实现的约束来源，不是 CLI 用法说明。

## 适用范围

适用于 ClawGraph 基于 proxy capture 的学习数据流：

```text
proxy facts
  -> evidence normalization and annotation
  -> slice registry and cohort curation
  -> dataset snapshots
  -> external training systems
  -> evaluation suites and scorecards
  -> routing coverage and rollout
  -> feedback and cohort refresh
```

ClawGraph 负责证据、治理、快照、评测资产和放量决策的边界管理。

ClawGraph 不负责：

- 真正的参数训练
- 在线 serving 基础设施本身
- 人工标注平台本身

## 分层原则

1. facts 只是证据，不是训练样本。
2. `session / run / request / branch` 属于执行层对象，`slice / cohort / dataset snapshot / eval suite` 属于治理层对象。
3. builder 不应直接面向“最新 run”，而应面向已经冻结的 cohort 或 dataset recipe。
4. 训练集切分和评测集治理必须分开；`golden`、`shadow` 不属于训练 split。
5. 所有替代与放量结论都必须按 task slice 成立，不能用“整体平均”掩盖问题。
6. fallback、disagreement、unknown subtype 必须回流到下一轮策展和评测，而不是直接沉没。

## 一等对象

这版设计要求把下面这些对象当成一等概念，而不是隐式逻辑：

| 对象 | 层级 | 回答的问题 |
| --- | --- | --- |
| `fact` / `artifact` / `semantic event` | evidence | 发生了什么 |
| `slice` | curation | 这是什么任务切片 |
| `candidate pool` | curation | 哪些执行记录可能属于这个切片 |
| `cohort` | curation | 哪批记录被批准进入后续构建 |
| `dataset recipe` | dataset | 用什么规则构建哪类训练集 |
| `dataset snapshot` | dataset | 哪一版 `train / val / test` 被冻结 |
| `eval suite` | evaluation | 用哪批 case 做离线、回归或影子验证 |
| `coverage policy` | release | 哪个切片允许小模型覆盖 |
| `rollout` | release | 当前处于哪一阶段放量 |

## 当前版本的核心结论

- 现有 proxy capture、artifact、builder、export 骨架可以继续沿用。
- 当前最需要补齐的不是新 builder，而是 `slice registry + cohort curation` 这一层。
- `golden`、`shadow` 应从训练集切分里移出，改为评测资产。
- 小模型替代应以切片覆盖和放量治理为中心，而不是“导出完数据就默认能替代”。

## 文档结构

- [证据采集与标注标准](./capture_and_labeling)
  定义 proxy 数据、标注字段、语义事件和进入策展层前的最低要求。
- [切片与 Cohort 策展标准](./cohort_curation)
  定义怎样把已有采集会话筛选、分类、聚合成稳定 cohort。
- [数据集快照与切分治理标准](./dataset_construction)
  定义怎样从 cohort 冻结出 `train / val / test` 和 manifest。
- [任务切片覆盖、训练配方与路由标准](./task_model_policy)
  定义什么 slice 适合什么训练配方、模型带宽、fallback 和 coverage。
- [评测、放量与回流标准](./replacement_validation)
  定义离线、golden、shadow、canary、回滚和回流机制。
- [ClawGraph 与 Logits 的训练、评测、替代集成方案](./logits_training_integration.zh-CN.md)
  定义怎样把 dataset snapshot 接到外部训练系统，并把 checkpoint 评测、promotion 和路由交接做成完整闭环。
- [长链路框架优化方案](./long_trajectory_optimization_plan.zh-CN.md)
  基于 `agent-diff` 复杂 agent run 的真实样本，定义 episode、branch、export、review 和后台编排的下一轮框架优化重点。
- [面向用户的 Dashboard 产品设计](./user_dashboard_prd.zh-CN.md)
  定义如何把以上分层能力组织成一套面向平台、训练、评估、PM 和 BD 的控制面板。
- [Dashboard 页面线框与交互流拆解](./user_dashboard_wireframes.zh-CN.md)
  继续拆解 Dashboard 的全局 shell、页面线框、对象详情模板和核心任务流。
- [Dashboard UI 产品化 Review 与改造 TODO](./dashboard_ui_productization_review.zh-CN.md)
  记录当前 Web 在流程清晰度、术语统一、上线接替表达上的问题，并拆成后续 UI 改造清单。

## 推荐实施顺序

1. 先补齐 [证据采集与标注标准](./capture_and_labeling) 中的 identity、task、verifier、quality 字段。
2. 再实现 [切片与 Cohort 策展标准](./cohort_curation) 中的 slice registry、candidate pool、cluster 和 cohort manifest。
3. 然后按 [数据集快照与切分治理标准](./dataset_construction) 固化 dataset recipe 和快照。
4. 再按 [ClawGraph 与 Logits 的训练、评测、替代集成方案](./logits_training_integration.zh-CN.md) 打通 snapshot、训练、评测和候选模型血缘。
5. 再按 [任务切片覆盖、训练配方与路由标准](./task_model_policy) 定义 coverage policy，而不是先选模型。
6. 最后严格按 [评测、放量与回流标准](./replacement_validation) 决定是否可以进入线上替代。

## 与当前 ClawGraph 能力的关系

当前系统已经具备：

- facts capture
- branch inference
- artifact bootstrap
- `sft` / `preference` / `binary_rl` builder
- readiness 和 export
- eval suite / scorecard / promotion decision
- Logits 训练请求、候选模型、评测执行和 router handoff 的桥接层
- Web 侧的数据治理面板，以及训练资产只读控制面

这些能力足以支撑 evidence layer 和单 run 导出。

仍需补齐的设计空白是：

- 真正持久化的 training registry，而不是仅依赖 manifest 扫描
- router / serving 对 promotion decision 的执行回执
- 独立的 coverage policy / route policy source-of-truth
- env-based RL 与更通用的 verifier-driven 评测执行器

## 约束等级

除非明确写为“可选”或“过渡态”，否则这里的规则都应视为默认设计标准。
