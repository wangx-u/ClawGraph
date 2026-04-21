# Dashboard 与生产数据链路落地计划

本文把后续落地拆成两个连续阶段：

1. 数据与 Dashboard 打通，用户可实时观测变化。
2. 生产级数据链路打通和抽象，trajectory gate、清洗、筛选、LLM-as-judge、人工介入都可插拔。

约束保持不变：

- 不为 `SWE-bench` 或某个 agent 写框架专用分支。
- 继续复用 ClawGraph 现有一等对象：`fact -> semantic event / artifact -> slice -> cohort -> dataset_snapshot / eval_suite`。
- 新能力优先落在 read model、worker、脚本或文档，不改写事实层。

## 当前实现对齐（2026-04）

这份 rollout 文档最初是实施计划。到当前版本，以下内容已经落地并应作为现状理解：

- 统一的 dashboard read model 已在 CLI、web bundle 和页面中共用
- 顶层 KPI 已统一为：
  `请求归属清晰度 / 任务标签覆盖率 / 决策语义覆盖率 / 已生成验证资产`
- 数据集、cohort、evaluation 详情页只展示真实 manifest 字段，不再填充演示值
- `local-store` 模式下，Web 侧可以直接执行人工复核闭环：
  `人工确认并入池 / 标记已人工确认 / 关闭当前事项`
- phase 2 已能从通用 `score` artifact 自动推导 scorecard 和 promotion
- 浏览器级回归已覆盖首页、接入页、manifest 详情页和人工复核关键路径
- benchmark collection 默认已切到 named instance pack，适合跨 repo、
  多任务类型的长期沉淀
- Web 已将 raw id 和原始接口路径降级为次要信息，主展示改为任务标题、
  仓库摘要和步骤类型
- Web 已补充训练资产控制面：
  `training request / model candidate / eval execution / router handoff`
  可以通过 manifest 目录进入同一个 dashboard bundle
- Training 详情页和 `clawgraph logits registry` 已共享同一份训练资产 read model，
  不再分别在 CLI 和 Web 各自拼装血缘关系
- Coverage 页面当前只展示真实 `candidate / decision / recommended stage / rollback conditions`
  不再把固定示例规则渲染成线上策略

因此，下文的阶段划分应理解为“设计与实现如何对应”，而不是“这些能力都还未开始”。

当前仍需明确的边界：

- 训练执行本身仍由外部 Logits 系统负责，Web 当前展示的是 store-backed 训练资产血缘与人工复核控制面
- 内建评测桥当前稳定支持的是基于对话样本的 offline eval；
  更通用的 env / verifier 执行器仍属于后续扩展

## 阶段 1：数据与 Dashboard 打通

### 目标

让用户在不离开 ClawGraph 对象模型的前提下，实时看到：

- 新 session / run / request 是否持续进入系统。
- 当前 run 到了 `E0 / E1 / E2` 哪一层。
- 哪些 run 已经满足学习型 builder 的 readiness。
- 哪些 slice 已经形成 cohort、dataset snapshot、eval suite、scorecard、feedback queue。

阶段 1 不要求先做完整 Web UI。第一步先落统一的 dashboard read model，再由 CLI、后续 API、前端共用。

### 设计

阶段 1 的 read model 只做投影，不新增 source-of-truth：

- `DashboardOverview`
  - `captured_sessions`
  - `captured_runs`
  - `e1_ready_runs`
  - `e2_ready_runs`
  - `export_ready_runs`
  - `frozen_cohorts`
  - `dataset_snapshots`
  - `active_eval_suites`
  - `scorecards_pass / hold / fail`
  - `feedback_queue_open`
- `DashboardSessionRow`
  - 一个 session 的 inbox 行，展示 run 数、ready 数、成功失败、分支数、最新更新时间。
- `DashboardRunRow`
  - 一个 run 的 readiness 与 evidence 行，展示 `task_family/task_type/task_instance_key`、语义事件、builder readiness。
- `DashboardSliceRow`
  - 一个 slice 的治理行，展示 cohort、snapshot、eval、scorecard、promotion、feedback 状态。

默认 dashboard 口径只看学习型 builder：

- `sft`
- `preference`
- `binary_rl`

原始 `facts` builder 仍然保留，但默认不纳入“export-ready”统计，避免把纯 capture 误算成训练资产。

### 里程碑

#### P1.1 统一快照接口

交付：

- `build_dashboard_snapshot(...)`
- `render_dashboard_snapshot(...)`
- `clawgraph inspect dashboard`

验收：

- 同一个 store 中的 session、run、slice、cohort、dataset、eval、feedback 能被一次性聚合。
- `--json` 输出可作为后续 API / UI 的稳定输入。

#### P1.2 Session Inbox 与 Run Readiness

交付：

- session 级 inbox 行
- run 级 `E0 / E1 / E2` 判定
- 学习型 builder readiness 汇总

验收：

- 一个 run 只有 capture 时显示 `E0`。
- 一个 run 有完整 annotation 时显示 `E1`。
- 一个 run 在 `E1` 基础上补齐 `task_completed` 与其他决策语义时显示 `E2`。
- `export_ready_runs` 只统计至少一个学习型 builder ready 的 run。

#### P1.3 Slice 治理总览

交付：

- slice 维度 cohort / snapshot / eval / scorecard / promotion / feedback 聚合

验收：

- 用户能从一个 slice 行看出它目前处于“仅采集 / 已冻结 / 已导出 / 已评测 / 有待处理反馈”的哪一步。

### 操作方式

当前推荐操作顺序：

```bash
clawgraph inspect dashboard --store sqlite:///clawgraph.db
clawgraph inspect dashboard --store sqlite:///clawgraph.db --json
clawgraph inspect dashboard --store sqlite:///clawgraph.db --builder sft
clawgraph inspect dashboard --store sqlite:///clawgraph.db --watch --interval-seconds 2
```

当后续 API / Web UI 落地时，应直接复用该 snapshot，而不是重新拼装 SQL 口径。

当前 `web/scripts/prod_dashboard_bundle.py` 也应复用共享 dashboard read model，不能自行推断 `E2` 或“可导出运行”。

### 保留到下一步的内容

以下内容不在阶段 1 首次落地范围：

- 浏览器 Dashboard 页面
- SSE / websocket 实时推送
- projector 持久化 read model
- 自动 bootstrap worker
- 自动 readiness worker

这些都应建立在 `inspect dashboard` 口径稳定之后再加。

## 阶段 2：生产级数据链路与分层可插拔

### 目标

把当前“能看见数据”升级为“能治理数据”，使以下流程自动化但可审计：

- trajectory 是否达标
- 数据清洗与标准化
- 任务分类与切片归属
- LLM-as-judge 标注
- 低置信样本进入 review queue
- 人工 accept / reject / override
- 进入 candidate pool、cohort freeze、dataset export、eval suite

### 分层合同

#### L0 原始事实层

- `fact`
- append-only
- 不可改写

#### L1 执行视图层

- `request span`
- `branch`
- `session / run` inspect view

#### L2 监督与判定层

- `annotation`
- `score`
- `preference`
- `critique`
- `judge verdict`
- `review decision`

全部通过 versioned artifact 追加，不允许原地修改历史标签。

#### L3 治理层

- `slice`
- candidate pool
- `cohort`
- `feedback queue`

#### L4 资产与决策层

- `dataset_snapshot`
- `eval_suite`
- `scorecard`
- `promotion_decision`

### 插拔点

阶段 2 只接受分层插件，不接受散落脚本：

- `capture_adapter`
  - 接不同 runtime / agent 的采集输入。
- `trajectory_gate`
  - 判定 run 是否达到 E0 / E1 / E2。
- `cleaner`
  - 做 redaction、normalization、去重、模板 hash 恢复。
- `classifier`
  - 做 taxonomy 分类与 task instance 恢复。
- `judge`
  - 做 LLM-as-judge，输出 versioned artifact。
- `review_sink`
  - 接人工审核、override、accept / reject。
- `curation_policy`
  - 决定哪些 artifact 可进入 candidate pool / cohort。
- `export_adapter`
  - 把 cohort 转成不同训练格式。
- `eval_adapter`
  - 把 snapshot 或 cohort 送入评测体系。

### 里程碑

#### P2.1 Trajectory Gate

交付：

- run 级 gate 结果
- gate 原因码
- 与 dashboard 中 `E0 / E1 / E2` 对齐的 machine-readable 结果

验收：

- open request 不可入 cohort。
- 没有 `task_instance_key` 的 run 不可入 `E1`。
- 没有稳定 verifier 的 run 不可入 RL / eval。

当前实现：

- `inspect dashboard` 已输出 `workflow_overview` 和 `workflow_runs`
- `inspect workflow` 已把单 run 的 `stage / blockers / review_reasons /
  next_action` 暴露成公共 CLI
- 每个 run 都会给出 machine-readable 的 `stage / blockers / next_action`
- 当前阶段划分为 `capture / annotate / augment / review / dataset / evaluate`
- `open_count > 0` 的 run 会被标记为 `capture`
- 缺少 E1 关键字段的 run 会被标记为 `annotate`
- 低置信或 feedback 命中的 run 会被标记为 `review`
- `E2 + ready_builders` 的 run 会被标记为 `evaluate`

#### P2.2 Clean + Classify

交付：

- 清洗 artifact
- taxonomy/classification artifact

验收：

- 同一批 raw facts 在同一版本下重复执行得到同样结果。
- `unknown` / `new_subtype` 被显式保留，不静默归到旧类。

#### P2.3 LLM-as-judge + Review Queue

交付：

- judge artifact
- 低置信流入 review queue
- supersede 链

验收：

- judge rerun 只会追加新 artifact，不破坏旧结论。
- `quality_confidence` 低于阈值的样本不会直接进入 cohort。

当前实现：

- 新增 `judge annotate`
- 支持 `heuristic` 和 `openai-compatible` 两类 provider
- judge 一律输出 versioned `annotation` artifact，不直接改事实层
- judge 结果里的 `review_reasons` 会进入 workflow / review queue 口径
- 新增 `feedback sync`，可把 slice review preview 变成去重后的 feedback
  queue 项

#### P2.4 Human Override

交付：

- 人工 accept / reject / override 也走 artifact 协议

验收：

- dashboard 可见 judge 结果被谁、何时、因何 override。
- candidate pool 与 readiness 会随着 override 变化而更新。

当前实现：

- 新增 `judge override`
- override 默认会追加一个 superseding annotation artifact，而不是覆盖旧结论
- override 后可选把对应 feedback 项标成 `reviewed` 或 `resolved`
- workflow 中会把这类 run 标成 `review_status=human`，页面显示为“已人工确认”

#### P2.5 自动策展与导出

交付：

- candidate pool 自动刷新
- cohort freeze 自动化
- dataset export 自动化
- eval suite 自动化

### 阶段 2 当前收尾

本轮已经把阶段 2 的第一条自动化主线落了出来，但仍然保持通用路径，没有
把 judge / review / curation worker 硬编码进任何 benchmark 或 agent
适配逻辑。

已完成：

- 在 `src/clawgraph/dashboard.py` 中新增 workflow 读模型
- 在 `src/clawgraph/dashboard.py` 中新增 `inspect_run_workflow(...)`
- 在 `src/clawgraph/judge.py` 中新增通用 judge 规划器
- 在 `src/clawgraph/curation.py` 中新增 `preview_slice_review_queue(...)`
- 在 `src/clawgraph/evaluation.py` 中新增
  `sync_feedback_queue_from_slice_review(...)`
- 在 `src/clawgraph/dashboard_bundle.py` 中导出 `workflowLanes`,
  `workflowRuns`, `ingestSummary`
- 首页、接入页、会话页、回放页改为围绕“采集 -> 补标签 -> 复核 ->
  导出/评估”展示真实数据
- UI 文案从内部术语切到对外展示可读的阶段说明、阻塞项和下一步动作
- 去掉多个页面里的硬编码 demo 路由，改为优先指向真实会话 / cohort /
  replay
- 新增 `judge annotate`、`feedback sync`、`feedback list`、`feedback enqueue`
  CLI 入口
- 新增 `judge override`、`feedback resolve` CLI 入口
- 增加 phase-2 回归测试，覆盖 heuristic judge、OpenAI-compatible judge
  解析、workflow 阶段推进、review queue 去重、人工 override 关闭反馈项

这一步的目标不是把自动 worker 一次做完，而是先把：

- 统一 machine-readable 口径
- 可追踪的下一步动作
- 对外展示也成立的流程视图
- judge / review queue 的最小自动化闭环

四件事稳定下来，再往后接 cleaner、classifier、cohort/export/eval worker。

验收：

- cohort freeze 后重复导出得到稳定 manifest。
- eval 使用的 taxonomy / judge / curation policy 版本可追溯。

## 当前已落地

本轮先落阶段 1 的 P1.1 / P1.2 骨架：

- 新增 `src/clawgraph/dashboard.py`
- 新增 `clawgraph inspect dashboard`
- 新增 `tests/test_dashboard.py`

当前实现特征：

- 统一聚合 execution + governance 对象
- 默认按学习型 builder 统计 readiness
- 通过现有 `fact / artifact / slice / cohort / dataset_snapshot / eval_suite` 建立视图

当前未落地：

- 持续刷新的 projector / worker
- 浏览器 Dashboard
- trajectory gate 独立服务化
- judge / review / curation worker 链路

## 最终验证用例

下面这些用例暂时保留为阶段收官验收，不应在初版 read model 里硬编码捷径。

### V1 实时观测闭环

步骤：

1. 启动 `clawgraph proxy`
2. 让一个 agent 经过 proxy 连续发起请求
3. 观察 dashboard snapshot

验收：

- 5 秒内能看到 session / run / request 数增加。
- run 关闭后 readiness 状态发生变化。

### V2 Annotation 到 readiness 闭环

步骤：

1. 对一个 run 追加 annotation artifact
2. 再追加 `route_decided` + `task_completed`

验收：

- 同一个 run 从 `E0 -> E1 -> E2` 可观察。
- `sft` 或 `binary_rl` readiness 变化可观察。

### V3 Judge 低置信拦截

步骤：

1. judge 产出 `quality_confidence` 低于阈值的 annotation

验收：

- run 不进入 candidate pool。
- review queue 出现新项目。

### V4 Human Override 可追溯

步骤：

1. 人工 override 一个 judge artifact

验收：

- 旧 artifact 保留
- 新 artifact 通过 `supersedes_artifact_id` 串起来
- dashboard 能展示 override 后的最新结论

推荐的本地终端验证命令：

```bash
PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main bootstrap openclaw \
  --store sqlite:////tmp/clawgraph-phase2-override.db \
  --session-id phase2_demo_session \
  --run-id phase2_demo_run

PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main slice register \
  --store sqlite:////tmp/clawgraph-phase2-override.db \
  --slice-id slice.demo \
  --task-family captured_agent_task \
  --task-type generic_proxy_capture \
  --taxonomy-version openclaw.taxonomy.v1 \
  --sample-unit run \
  --verifier-contract openclaw.verifier.v1 \
  --risk-level medium \
  --default-use training_candidate \
  --owner demo

PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main feedback enqueue \
  --store sqlite:////tmp/clawgraph-phase2-override.db \
  --slice-id slice.demo \
  --source auto_review \
  --target-ref run:phase2_demo_run \
  --reason low_quality_confidence

PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main inspect workflow \
  --store sqlite:////tmp/clawgraph-phase2-override.db \
  --session phase2_demo_session \
  --run-id phase2_demo_run --json

PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main judge override \
  --store sqlite:////tmp/clawgraph-phase2-override.db \
  --session phase2_demo_session \
  --run-id phase2_demo_run \
  --review-note "operator confirmed this run can enter the dataset pool" \
  --feedback-status resolved \
  --slice-id slice.demo \
  --reviewer demo --json

PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main inspect workflow \
  --store sqlite:////tmp/clawgraph-phase2-override.db \
  --session phase2_demo_session \
  --run-id phase2_demo_run --json
```

期望：

- override 前 `stage=review`
- override 后 `stage=dataset`
- override 后 `review_status=human`
- 对应 feedback item 变成 `resolved`

### V5 Export 与 Eval 可回溯

步骤：

1. freeze cohort
2. export dataset
3. create eval suite
4. record scorecard
5. record promotion decision

验收：

- 每一步都能回溯到 slice、cohort、dataset_snapshot、scorecard 版本。
- 同一批 cohort 重复导出得到稳定成员集合。
