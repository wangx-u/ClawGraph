# Phase 2 最终实现报告

本文记录 ClawGraph phase 2 的最终落地状态、关键实现、真实联调结果和
可复跑入口。

## 1. 目标与边界

本次 phase 2 保持以下边界不变：

- 不为 `mini-SWE-agent` 或 `SWE-bench` 写框架专用兼容逻辑
- 继续复用 ClawGraph 既有对象模型：
  `fact -> artifact -> slice -> cohort -> dataset_snapshot / eval_suite / scorecard / promotion`
- benchmark 相关逻辑仅体现在脚本、配置和验证文档，不进入框架核心分支

最终状态不是“还能继续做的原型”，而是“已经可直接使用的通用链路”：

1. proxy 捕获真实 agent 流量
2. trajectory prepare / clean / gate
3. LLM-as-judge 产出 versioned annotation
4. 低置信样本进入 review
5. human override 通过 supersede 链接管
6. 自动形成 slice / cohort / dataset export / eval suite / scorecard /
   promotion decision
7. dashboard snapshot 和 web bundle 能直接读取同一份 live store

## 2. 核心实现

### 2.1 数据准备与清洗

新增：

- [src/clawgraph/redaction.py](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/redaction.py)
- [src/clawgraph/prepare.py](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/prepare.py)

提供的通用能力：

- secret-like 内容检测与脱敏
- run 级 prepare summary
- `prepare_status = clean / review / blocked`
- blocker / review reason 统一归因

### 2.2 Phase 2 编排

新增：

- [src/clawgraph/phase2.py](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/phase2.py)

新增 CLI：

- `clawgraph phase2 run`
- `clawgraph eval create-suite`
- `clawgraph eval record-scorecard`
- `clawgraph eval decide-promotion`

编排能力覆盖：

- prepare artifact 生成
- judge annotation 生成与持久化
- slice 自动注册
- feedback queue sync
- training cohort freeze
- holdout/evaluation cohort freeze
- dataset export
- eval suite / scorecard / promotion decision

当前实现已经进一步收敛为：

- 当 run 或 evaluation cohort 中存在通用 `score` artifact 时，
  `phase2 run` 可以自动推导 scorecard
- 在未显式传入 `scorecard_metrics / scorecard_thresholds` 时，也能继续生成
  promotion decision
- `run_phase2_live_validation.sh` 已切换到自动闭环路径，不再手工注入固定
  scorecard 指标

### 2.3 Judge 与人工复核

扩展：

- [src/clawgraph/judge.py](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/judge.py)

提供：

- `heuristic` 和 `openai-compatible` judge provider
- `judge annotate`
- `judge override`
- supersede 链
- review reason 统一口径

### 2.4 Dashboard 与 UI 口径统一

扩展：

- [src/clawgraph/dashboard.py](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/dashboard.py)
- [src/clawgraph/dashboard_bundle.py](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/dashboard_bundle.py)
- [web/src/lib/data-source.ts](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/web/src/lib/data-source.ts)

并调整了对外文案：

- `补标签` -> `数据准备`
- `样本治理` -> `数据筛选`
- `回流` -> `人工复核`
- `任务识别清晰度` -> `任务标签覆盖率`
- `语义覆盖率` -> `决策语义覆盖率`
- `可评估运行` -> `已生成验证资产`

目的不是改对象模型，而是让展示更专业、流程更清楚、空态不再混入 mock
叙事。

当前 UI 还额外收敛了两点：

- session / run 以任务标题、仓库和实例摘要为主，原始 `sess_xxx` /
  `run_xxx` 只作为次级信息保留
- replay / access 以步骤类型和摘要为主，原始 `/chat/completions` 路径
  只保留为技术明细

### 2.5 Web 可操作闭环与浏览器回归

新增：

- [web/src/app/feedback/actions.ts](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/web/src/app/feedback/actions.ts)
- [web/src/lib/dashboard-actions.ts](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/web/src/lib/dashboard-actions.ts)
- [web/scripts/prod_dashboard_action.py](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/web/scripts/prod_dashboard_action.py)
- [web/e2e/dashboard-regression.spec.ts](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/web/e2e/dashboard-regression.spec.ts)

当前 Web 侧已经不是只读监控面板，而是具备以下能力：

- 在 `local-store` 模式下直接完成人工确认、标记 reviewed、关闭 feedback
- 数据集 / cohort / evaluation 详情页只展示真实 manifest 字段，不再展示伪造信息
- 用 Playwright 覆盖首页、接入页、详情页和人工复核关键路径
- 用真实 bundle 验证“人类可读标题 + 真实 manifest + 可操作复核”这一套
  对外展示路径

## 3. 关键修复

### 3.1 修复 `phase2 run` 的 live judge 路径

问题：

- `resolve_e1_annotation_for_run(...)` 会把非 E1 artifact 一并合并
- live judge 未成功持久化时，prepare artifact 会被误当成“非空 annotation”
- 进而触发：
  `task_family is required to build the phase2 slice`

修复：

- [src/clawgraph/artifacts/annotations.py](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/artifacts/annotations.py)
  现在只解析 active E1 annotations
- [src/clawgraph/phase2.py](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/src/clawgraph/phase2.py)
  现在只有在 E1 必填字段完整时才自动建 slice，否则明确停留在
  `annotate / review`

### 3.2 复用现有 live proxy/store

新增：

- [benchmarks/swebench_lite/run_phase2_live_validation.sh](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/benchmarks/swebench_lite/run_phase2_live_validation.sh)

支持两种模式：

1. 自己启动新 proxy
2. 复用现有 `EXISTING_PROXY_BASE + STORE_URI`

这让同一个脚本既能用于全新联调，也能用于已有现场环境的验证。

## 4. 真实联调结果

最终 live store：

- `/tmp/clawgraph-phase2-final-live.db`

最终 phase 2 导致的核心对象：

- slice:
  `slice.captured_agent_task.generic_proxy_capture.7513daa2`
- training cohort:
  `cohort_b3ac60f7d61549dd9c39b57684ee5db2`
- evaluation cohort:
  `cohort_4e9f9996c32843c18680c63a29d7a09c`
- eval suite:
  `eval_11063756a6894d3f88f65f43076b99f3`
- scorecard verdict:
  `pass`
- promotion decision:
  `promote`

phase 2 的真实执行轨迹写入：

- `/tmp/clawgraph-phase2-existing-report/run1.initial.json`
- `/tmp/clawgraph-phase2-existing-report/run1.rerun.json`
- `/tmp/clawgraph-phase2-existing-report/run2.initial.json`
- `/tmp/clawgraph-phase2-existing-report/run2.rerun.json`
- `/tmp/clawgraph-phase2-existing-report/phase2.slice.json`

其中真实状态演进为：

- `run1.initial.json`: `stage=review`
- `run1.rerun.json`: `stage=dataset`
- `run2.initial.json`: `stage=review`
- `run2.rerun.json`: `stage=dataset`

这说明：

1. LLM-as-judge 先正常产出 review
2. human override 通过通用 supersede 链完成兜底
3. rerun 后自动进入 dataset/export
4. slice 范围内继续完成 eval / scorecard / promotion

dashboard 真实快照：

- `/tmp/clawgraph-phase2-existing-report/dashboard.after.json`

其中关键指标：

- `captured_sessions = 5`
- `captured_runs = 5`
- `e1_ready_runs = 2`
- `export_ready_runs = 2`
- `dataset_snapshots = 3`
- `active_eval_suites = 1`
- `scorecards_pass = 1`

web 读取的同口径 bundle：

- `/tmp/clawgraph-phase2-existing-report/dashboard.bundle.json`

说明：

- live store 的 CLI snapshot、web bundle 和页面读取逻辑已经统一到同一份
  `dashboard_bundle` 读模型
- 后续补充的浏览器回归已覆盖首页、接入页、manifest 详情页和人工复核操作
- 因此当前不是“只有 bundle JSON 对齐”，而是“页面口径和关键交互也已经完成验证”

## 5. mini-SWE-agent 真实接入证据

在同一个 live proxy/store 上，mini-SWE-agent 产生了真实 benchmark 会话：

- session:
  `sess_8021a8a3c45145b7a285692552e20fbf`
- run:
  `run_20e905d5381d4810b26d14fd0b3713b8`

其捕获事实明确显示：

- 请求路径是 `/chat/completions`
- 模型名是 `deepseek-chat`
- 首条 prompt 以
  `You are a helpful assistant that can interact with a computer shell...`
  开头
- 该 run 内持续出现多轮 request / response 往返

这证明：

- mini-SWE-agent 不是停在本地准备阶段
- 它确实把 LLM 请求打进了同一个 ClawGraph proxy
- proxy、phase 2、dashboard 读到的是同一份真实 benchmark 流量

## 6. 可复跑入口

全新启动模式：

```bash
DEEPSEEK_API_KEY=your-real-key \
bash benchmarks/swebench_lite/run_phase2_live_validation.sh
```

复用现有 live proxy/store：

```bash
DEEPSEEK_API_KEY=your-real-key \
STORE_URI=sqlite:////tmp/clawgraph-phase2-final-live.db \
EXISTING_PROXY_BASE=http://127.0.0.1:8091 \
OUTPUT_DIR=/tmp/clawgraph-phase2-existing-report \
bash benchmarks/swebench_lite/run_phase2_live_validation.sh
```

## 7. 长时 benchmark collection 结果

本轮还额外完成了一次“用户视角”的长时联调：

- 一个终端运行 live proxy
- 一个终端运行 live dashboard
- 同一个 store 中顺序跑多个 `mini-SWE-agent` benchmark 实例
- 每个实例结束后自动 enrich、phase2、export
- 最后再做一次 slice 级冻结与导出

实际使用的 store 和输出目录：

- store:
  `/tmp/clawgraph-benchmark-collection.db`
- output:
  `/tmp/clawgraph-benchmark-collection-out`

真实 benchmark 会话：

- `sess_7fb142ed9eab434988c25f9780e33e76` /
  `run_68e6a78fd0ce4482b8ae9a540fb2d731`
- `sess_708bdf7708484874a16a1091f95f7fbe` /
  `run_bb5fdd532adb4d469ea96322b4463194`

这次 collection 的最终结果：

- `captured_sessions = 2`
- `captured_runs = 2`
- `e1_ready_runs = 2`
- `export_ready_runs = 2`
- `dataset_snapshots = 3`
- `active_eval_suites = 1`

专项 benchmark 数据沉淀结果：

- `sqlfluff__sqlfluff-1625` 单 run SFT 导出：`30` 条
- `sqlfluff__sqlfluff-2419` 单 run SFT 导出：`45` 条
- slice 级训练导出：
  `/tmp/clawgraph-benchmark-collection-out/phase2/final-slice/cohort_3a198cd33b434595876df24a4ba63abd.sft.jsonl`
  共 `30` 条
- slice 级评测 cohort：
  `cohort_3d5d11e75b1c41b38b98326b84ad0a88`
- eval suite：
  `eval_a38e9e1a0a014377a281166405062430`

需要特别说明的是，最终 slice 级训练导出不是 `30 + 45 = 75` 条。
这是因为 slice 冻结时使用了 `holdout_fraction=0.34` 和
`max_members_per_task_instance=1`，第二个 benchmark run 被正确放入
evaluation/holdout cohort，而不是丢失。

这轮长跑里顺手做的系统收敛包括：

- collection 脚本自动识别本地 `SWE-Bench Lite` 缓存并切到
  `offline-cache`，避免每次首轮都卡在 HuggingFace 元数据探测
- 继续复用本地 testbed 的 GitHub archive fallback，避免 `git fetch`
  的 HTTP2 抖动把整轮 collection 打断
- 把 dashboard 对外文案进一步收敛成
  `请求归属清晰度 / 任务标签覆盖率 / 决策语义覆盖率 / 已生成验证资产`
  这类更适合展示和排障的说法
- 把 Web 反馈页补成可操作闭环，而不再要求用户回到 CLI 完成人工复核
- 补齐浏览器级回归，保证这些对外页面和关键路径不会静默回退到伪数据

## 8. 结论

phase 2 已经达到“完整直接可用”的状态：

- 主链路完整
- 低置信 review 与人工 override 都可用
- export / eval / promotion 已串通
- Web 页面已和真实 store / manifest / feedback 写操作对齐
- 浏览器级回归已覆盖关键产品路径
- mini-SWE-agent + proxy + dashboard 已在真实 store 上联通
- 保持了通用适配，没有为 benchmark 写框架专用分支
