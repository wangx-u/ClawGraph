# ClawGraph 长链路框架优化方案

## 1. 文档目的

本文记录一轮基于 `agent-diff + clawgraph` 长链路样本的框架级 review，并给出后续优化方案。

这份方案只关注 `ClawGraph` 的服务能力、数据能力和治理能力，不讨论下面这些主题：

- SSO / JWT / RBAC
- 市场宣发文案
- 页面视觉层的小范围修饰

本文要回答的问题是：

1. 当 agent 任务从短链路变成长链路后，`ClawGraph` 当前框架哪里开始暴露不足。
2. 这些不足更偏“表现层问题”还是“核心模型/服务能力问题”。
3. 后续应该怎样分阶段把 `ClawGraph` 从“能采、能看、能导”推进到“能稳定支撑复杂 agent episode 的控制面”。

## 2. 样本依据

本轮判断不是抽象推演，而是来自真实跑出来的 `agent-diff` 长链路样本。

### 2.1 已验证的复杂样本

#### A. Cross-channel Summarization

- suite: `Slack Bench v2 (Combined)`
- session: `sess_3df6a0935f2244cfaadf731650d99b3f`
- run: `run_340ca1ad83b0487ca89b1ca37afa9c1b`
- request 数: `8`
- 结果: `passed=true`, `score=1.0`

特点：

- 先检索 channel 列表和消息历史
- 再汇总结果并发送到新 channel
- 已经明显不是单轮“发一条消息”的短任务

#### B. Cricket World Cup Watch Party

- suite: `Slack Bench v2 (Combined)`
- session: `sess_34bca8c4eb294367a14550b72b81c330`
- run: `run_8edd24cc1db04716bba600791cd2fce9`
- request 数: `18`
- 结果: `passed=true`, `score=1.0`
- diff summary: `inserts=7`, `updates=1`, `deletes=1`

特点：

- 检索 channel 和历史消息
- 创建新 channel
- 修改 topic
- 更新已有消息
- 删除旧消息
- 打开 DM 并发送多条通知

这是目前最典型的长链路成功样本。

#### C. Thread Q&A from DM - Circuit Tracer Rewrite

- suite: `Slack Bench v2 (Combined)`
- session: `sess_7993a30f4af144eaaf6e35a362323477`
- run: `run_5180fa9d27e04a15a563eefabb1a20f1`
- request 数: `12`
- 结果: `passed=false`, `score=0.5`

特点：

- agent 最终自述“任务完成”
- verifier 明确认定没有完全满足任务要求
- 这是复杂失败样本，不是简单 API 调错

### 2.2 这批样本带来的直接观察

1. `ClawGraph` 已经能稳定捕获长链路 run，不会在 request 数上崩掉。
2. `ClawGraph` 已经能把这些 run 推进到 `E1 / export_ready`。
3. 复杂样本一旦进入 `phase2`，就开始暴露更深层的框架问题，而不是简单的 UI 呈现问题。

## 3. 总体判断

当前 `ClawGraph` 的真实能力可以概括成一句话：

> 已经能承载复杂 agent run，但还没有把复杂 agent run 提升成“可解释、可治理、可调度的 episode 级对象”。

也就是说，系统现在更像：

- 一个对长链路也能工作的 `proxy capture + data governance` 骨架

而还不像：

- 一个真正面向长链 agent 的 `episode control plane`

这次长链路验证中暴露的主要问题，不是“采不到”，而是下面这些：

- 步骤语义不够
- 分支语义不够
- 训练样本抽样策略不够
- review gate 颗粒度不够
- verifier 失败定位不够
- 批量采集与后台编排能力不够
- 读模型和回放能力在复杂场景下不够经济

## 4. 核心问题清单

### P0. 长链路被压扁成很多次 `/chat/completions`

现象：

- `Cricket World Cup Watch Party` 在 replay 里主要表现为 `18` 个 `/v1/chat/completions`
- request group 很完整，但服务步骤本身不可见
- 实际发生过的 `create / setTopic / update / delete / DM notify` 没有成为一等步骤对象

根因：

- 当前主采集面仍是 proxy request/response
- `build_request_span_summaries(...)` 的核心对象仍是 HTTP request span，而不是 agent step
- 对长链任务来说，模型轮次只是执行过程的一部分，不是完整流程的自然单位

影响：

- 回放可用，但不够解释性
- 失败定位会落回人工阅读 prompt/response
- UI 很容易退化成“18 次 LLM 调用”，而不是“18 步任务流程”

### P0. 关键分支仍然主要依赖推断恢复

现象：

- 长链路 run 的 workflow blocker 多次出现“关键分支仍主要依赖推断恢复”
- dashboard 中也存在 `semantics=<none>` 的情况
- branch 结构主要依赖 `infer_branches(...)`，而不是 runtime 主动声明

根因：

- 现在的 branch 语义主要从请求序列推导
- runtime / tool executor / verifier 没有稳定上报 branch reason 和 step reason

影响：

- 复杂任务越长，推断误差越容易累积
- 影响后续 judge、review、export 对真实流程的还原

### P0. 长链路天然在 SFT 中占更高权重

现象：

- 复杂 slice 的 `5` 条 run 被导成 `41` 条 SFT record
- 同一条 run 的 request 越多，对训练集贡献越大

根因：

- 当前 `sft` builder 的主导出单位是 request
- 复杂任务没有单独的 episode-level 采样治理

影响：

- 长链路 run 会在训练集中被自然放大
- 这可能让“更复杂但更少见”的任务在训练时占比失真
- 后续用 `logits` 训练时，模型会更偏向长 run 的响应风格和工具调用格式

### P0. 复杂失败样本会阻断整批导出

现象：

- 当前复杂 slice 已成功冻结 cohort
- 但因为有 `2` 条低分样本在 review queue，整批 dataset snapshot 没有真正导出

根因：

- 当前导出 gate 只要看到 `review.required = true` 就整体阻断
- gate 以 cohort 为单位，不区分 clean member 和 review member

影响：

- 长链路任务天然更容易产生复杂失败样本
- 如果沿用当前 gate，复杂 benchmark 数据流很容易频繁“整批出不了数”

### P1. verifier 结果过于粗糙，复杂失败缺少定位信息

现象：

- 当前 run 级主要沉淀的是 `score` 和最终 diff summary
- 对复杂失败样本，只能知道“失败了”，很难直接知道“失败在哪一步”

根因：

- `score artifact` 目前更偏 run-level verdict
- 没有把 verifier 的结构化差异拆进 step/stage 维度

影响：

- review queue 很难做高效人工处理
- 后续也难以基于失败类型做 slice 或 auto-judge 改善

### P1. 批量长链路采集仍主要依赖脚本编排

现象：

- 本轮复杂链路收集仍然依赖 shell loop 和 benchmark script
- `phase2`、`export`、`logits prepare-sft` 仍主要是串脚本推进

根因：

- 当前系统缺少正式的后台 job 模型
- 缺少 batch benchmark collection 的状态机和恢复点

影响：

- demo 可以跑
- 持续生产复杂 benchmark 数据会越来越依赖人工编排
- 失败恢复、断点续跑、最小成功数控制都不够系统化

### P1. 复杂回放的读模型成本过高

现象：

- dashboard bundle 和 replay 仍然大量依赖现算
- 构建 bundle 时会按 session/run/fact/artifact 多轮读取

根因：

- 当前缺少真正的 projector/read model
- Web 端更多是在动态拼装 store 内容，而不是读取增量维护的视图

影响：

- 当前样本规模还能接受
- 一旦 benchmark pack 和长链 episode 数量上来，刷新成本会迅速升高

## 5. 目标状态

面向长链 agent，`ClawGraph` 的目标不应只是：

- 记录事实
- 导出样本

而应是：

1. 能把一次复杂 agent run 表达成 episode + steps + branch decisions
2. 能区分 clean / review / quarantine / holdout 四类后续处置
3. 能把 verifier 结果映射到失败步骤和失败类型
4. 能把批量 benchmark collection 当作后台任务来编排
5. 能把复杂 replay 和 dashboard 依赖的统计结果提前投影出来

## 6. 优化方案

### W1. 引入 episode/step 语义层

目标：

- 让 `ClawGraph` 的一等对象从“request span”扩展到“agent step”

建议新增的事件类型：

- `tool_call_started`
- `tool_call_finished`
- `env_read`
- `env_mutation`
- `verifier_checked`
- `rollback_applied`
- `plan_updated`
- `retry_started`
- `retry_finished`

建议新增的 step 字段：

- `step_id`
- `step_type`
- `step_label`
- `parent_step_id`
- `branch_id`
- `resource_kind`
- `resource_ref`
- `expected_effect`
- `observed_effect`

落地方式：

- `proxy` 继续负责底层模型 request capture
- `runtime client` 和 benchmark adapter 负责补高层语义事件
- replay 和 dataset export 都优先读取 step 语义，而不是只读 request span

### W2. 把 branch 从推断对象升级为声明对象

目标：

- 减少复杂链路中 `inferred_only_branching`

建议：

- runtime 在如下情形主动上报 branch reason：
  - retry
  - fixup
  - rollback
  - explore
  - finalize
- branch 结构增加：
  - `reason`
  - `source`
  - `decision_basis`
  - `opened_by_step_id`
  - `closed_by_step_id`

落地收益：

- replay 更像流程图
- review 和 judge 更容易知道某段链路是主流程、修复流还是回滚流

### W3. 为长链路提供 episode-aware 训练导出

目标：

- 避免“长 run 自动占更多训练权重”

建议支持三种导出模式：

1. `step_sft`
   - 每个 step 1 条样本
   - 适合模仿工具调用与局部决策
2. `episode_sft`
   - 每个 run 或 step chunk 1 条样本
   - 适合复杂任务摘要式训练
3. `hybrid_sft`
   - 每个 run 限制最大 step 样本数
   - 对长 run 做配额或 downweight

建议补充的 manifest 字段：

- `records_per_run`
- `records_per_task_instance`
- `export_mode`
- `max_records_per_run`
- `sample_weighting_policy`

### W4. 把 review gate 从整批阻断改成分层治理

目标：

- 让复杂 benchmark 数据流可以持续出数

建议把 cohort 成员分成：

- `eligible`
- `quarantined`
- `heldout`
- `blocked`

并支持两种导出策略：

1. `strict_export`
   - 当前行为
   - 有 review queue 就整体阻断
2. `quarantine_export`
   - clean 成员先导出
   - review 成员进入 quarantine bucket
   - manifest 显式记录被排除成员及原因

这样长链路复杂失败样本不会拖垮整批可训练数据。

### W5. 扩展 verifier / score artifact，提供失败定位

目标：

- 让复杂失败样本可 review、可统计、可筛选

建议 score artifact 增加：

- `failure_stage`
- `failure_step_type`
- `failed_assertion`
- `expected_effect`
- `observed_effect`
- `entity_refs`
- `repro_hint`

建议新增 failure taxonomy：

- `missing_read`
- `wrong_target`
- `partial_update`
- `incorrect_summary`
- `missing_notification`
- `premature_success_claim`

这样：

- review queue 可以按失败类型排序
- 后续可以为某类复杂失败单独建 slice

### W6. 把 benchmark collection 升级成后台任务

目标：

- 摆脱脚本驱动的长链路采集方式

建议新增 job 类型：

- `collection_job`
- `phase2_job`
- `export_job`
- `training_prepare_job`

每类 job 至少有：

- `status`
- `attempt_count`
- `started_at`
- `finished_at`
- `last_error`
- `resume_from`
- `target_store`
- `pack_spec`

对长链 benchmark，系统需要原生支持：

- 最小成功数
- 最大失败数
- 失败后继续
- 断点续跑
- 自动进入下一阶段

### W7. 建立 projector/read model

目标：

- 降低复杂 replay 和 dashboard 的实时拼装成本

建议新增投影视图：

- `run_summary_view`
- `workflow_view`
- `step_timeline_view`
- `review_queue_view`
- `training_registry_view`

设计原则：

- facts/artifacts 仍保持 immutable
- projector 增量消费事实，生成只读视图
- Web 和 CLI 优先读视图，不再多轮全表扫 store

### W8. 为复杂轨迹增加服务健康指标

当前复杂场景下最有价值的指标，不再只是 `sessions/runs`，而应增加：

- `avg_steps_per_run`
- `p95_steps_per_run`
- `runs_with_declared_steps_ratio`
- `runs_with_declared_branch_ratio`
- `failed_runs_with_failure_stage_ratio`
- `quarantined_member_ratio`
- `records_per_run_distribution`
- `phase2_blocked_by_review_count`

这些指标比单纯 `E1/export_ready` 更能揭示复杂 agent 数据流的真实健康度。

## 7. 模块级改造建议

### 7.1 `runtime` / `proxy`

优先补：

- runtime-side semantic event emitter
- step-aware fact schema
- richer branch declaration

相关模块：

- `src/clawgraph/runtime/client.py`
- `src/clawgraph/runtime/openai.py`
- `src/clawgraph/proxy/server.py`
- `src/clawgraph/protocol/*`

### 7.2 `graph` / `inspect` / `replay`

优先补：

- `RequestSpanSummary` 之外的 `StepSummary`
- run replay 的 step timeline
- branch reason / step reason 的直出

相关模块：

- `src/clawgraph/graph/inspect.py`
- `src/clawgraph/dashboard_bundle.py`
- `src/clawgraph/cli/main.py`

### 7.3 `prepare` / `judge` / `evaluation`

优先补：

- prepare 对复杂轨迹的 step completeness 判断
- score artifact 的 failure taxonomy
- review queue 的 richer reason payload

相关模块：

- `src/clawgraph/prepare.py`
- `src/clawgraph/judge.py`
- `src/clawgraph/evaluation.py`

### 7.4 `export` / `phase2`

优先补：

- `episode_sft` / `hybrid_sft`
- quarantine export
- records-per-run manifest

相关模块：

- `src/clawgraph/export/dataset.py`
- `src/clawgraph/export/readiness.py`
- `src/clawgraph/phase2.py`

### 7.5 `dashboard` / `training registry`

优先补：

- read model / projector
- run/step timeline payload
- benchmark batch job 状态读模型

相关模块：

- `src/clawgraph/dashboard.py`
- `src/clawgraph/dashboard_bundle.py`
- `src/clawgraph/integrations/logits/registry.py`

## 8. 实施顺序

### Phase A: 让长链路“看得懂”

交付：

- step semantic events
- declared branch reasons
- replay step timeline

验收：

- 像 `Cricket World Cup Watch Party` 这类 run，在 replay 中能直接看到“检索 / 创建 / 修改 / 删除 / 通知”的步骤流

### Phase B: 让长链路“导得稳”

交付：

- quarantine export
- episode-aware SFT export
- records-per-run manifest

验收：

- 复杂 slice 中即使混有失败样本，也能稳定导出 clean 子集
- 长 run 不会无约束地主导训练样本数量

### Phase C: 让长链路“批量跑得动”

交付：

- collection job
- phase2/export/training prepare job
- 可恢复的后台执行模型

验收：

- 长链 benchmark collection 不再依赖 shell loop 才能稳定运行

### Phase D: 让长链路“评得清”

交付：

- richer verifier artifact
- failure taxonomy
- review queue enriched reason payload

验收：

- 复杂失败样本能直接知道失败发生在哪个阶段和步骤类型

### Phase E: 让长链路“读得快”

交付：

- projector
- run/step/workflow/readiness views

验收：

- dashboard 和 replay 不再依赖高成本现算

## 9. 测试方案

### 9.1 单元测试

- step semantic event schema
- branch declaration schema
- export weighting policy
- quarantine export gate
- failure taxonomy rendering

### 9.2 集成测试

- `agent-diff` 长链成功样本
- `agent-diff` 长链失败样本
- mixed clean/review cohort export
- batch collection job resume/retry

### 9.3 基准验证

建议固定一组复杂样本作为长期回归集：

- `Cross-channel Summarization`
- `Cricket World Cup Watch Party`
- `Thread Q&A from DM - Circuit Tracer Rewrite`

重点看：

- replay 的步骤可读性
- branch source 比例
- complex failure 的定位粒度
- export 的可持续性

## 10. 结论

从长链路 `agent-diff` 的实际运行结果看，`ClawGraph` 现在已经证明了自己可以：

- 稳定采集复杂 agent run
- 形成 E1 级可治理证据
- 进入 slice/cohort/export 这条主线

但还没有证明自己已经具备：

- episode 级步骤语义
- 复杂失败的定位能力
- 长链路训练样本的分布控制
- 面向批量 benchmark 的服务化编排能力

因此，下一轮框架优化最值得投入的方向，不是继续补页面，而是把 `ClawGraph` 从“复杂 run 的采集与治理骨架”升级成“复杂 run 的 episode control plane”。
