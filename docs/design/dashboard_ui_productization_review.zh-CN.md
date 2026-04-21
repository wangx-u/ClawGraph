# ClawGraph Dashboard UI 产品化 Review 与改造 TODO

## 1. 文档目的

本文记录一次基于真实 Web 页面、设计文档和当前实现代码的 UI review。

目标有两个：

1. 把当前产品在 `proxy -> step / trajectory -> 自动判断 / 自动筛选 -> dataset snapshot -> logits training -> eval -> model handoff` 这条链路上的 UI 问题记录下来。
2. 把改造建议拆成可执行的 TODO list，供后续产品、设计和前端实现直接使用。

本文聚焦产品层和交互层，不重复记录已经顺手修掉的小实现 bug。

## 2. 当前产品闭环判断

从对象和页面覆盖度看，当前 ClawGraph Web 已经具备完整骨架：

```text
接入 proxy
  -> 查看 session / run / replay
  -> supervision 自动判断
  -> curation 候选筛选 / cohort 冻结
  -> dataset snapshot
  -> 外部 Logits 训练请求 / candidate
  -> eval suite / scorecard
  -> coverage / promotion
  -> router handoff
  -> feedback 回流
```

因此，当前问题不是“缺少页面”，而是“页面之间没有被组织成一条自然、稳定、对外可讲清楚的生产闭环”。

## 3. 总体结论

### 3.1 已经具备的优点

- 一等对象已经基本齐全。
- 主信息大多已经从 raw id 下沉到任务标题、任务摘要、步骤类型。
- `dataset -> training -> evaluation -> handoff` 的后半程资产链已经成形。
- `coverage` 和 `handoff` 已经开始使用真实字段，而不是纯演示文本。

### 3.2 当前最核心的问题

当前 UI 仍然明显偏向：

- object-first，而不是 workflow-first
- operator-first，而不是 external-facing
- evidence browsing，而不是 launch control

结果是：

- 工程同学可以理解页面
- 内部熟悉对象模型的人可以顺着用
- 外部用户、PM、BD、方案负责人仍然需要自己脑补“现在在哪一步、下一步是什么、为什么能进入下游”

这使产品还不够“生产级可对外”。

## 4. 主要问题清单

### P0. 顶层信息架构仍按对象拆分，而不是按流程组织

现状：

- 一级导航按 `总览 / 接入 / 最近运行 / 数据准备 / 数据筛选 / 数据集 / 训练资产 / 评测 / 替代建议 / 人工复核` 展开。
- “最近运行”和“回放”在用户侧心智里仍是同一件事。
- 没有统一的“当前阶段 / 上一步 / 下一步”全局流程指示器。

影响：

- 用户需要自己理解 `session / replay / supervision / curation / datasets / training / evaluation / coverage` 的关系。
- 这会直接削弱首访理解效率和对外演示的说服力。

### P0. 首页首屏仍是“预览说明”，不是“闭环控制台”

现状：

- 首页最上面首先强调“定向预览”“不是完整托管平台”“当前边界”。
- 这些信息对内是必要的，但在首屏占据了最高层级。

影响：

- 对外演示时，用户先感知到“不成熟”，而不是“流程可控、资产可追溯、替代可验证”。
- 产品信心被 UI 自己先削弱。

### P0. 前半程缺少明确的 trajectory gate / eligibility 视图

现状：

- Replay 页能看到步骤、请求、分支和一些下一步提示。
- 但看不到明确的 `trajectory gate` 结果。
- 用户很难一眼判断：
  - 为什么这条 run 只能停在 replay
  - 为什么它已经能进入 supervision / curation
  - 还缺哪些字段才能变成 dataset-ready

影响：

- `proxy -> step -> trajectory -> 自动判断 -> 自动筛选` 这条链路在 UI 中没有一个明确“闸门”。
- 需要用户通过多页跳转自行推断。

### P0. 状态体系过多，缺乏统一用户态

现状：

- 页面混用了 `E0 / E1 / E2`
- 同时又有 `capture / annotate / augment / review / dataset / evaluate`
- 还有 `可筛选 / 可评估 / 待复核 / 已人工确认` 等不同口径

影响：

- 内部实现可以接受，但对外会显得状态机不稳定。
- 用户不容易形成统一的阶段认知。

### P1. Supervision 和 Curation 仍偏 operator-first

现状：

- supervision 主要围绕 `artifact type / targetRef / producer / version` 展开
- candidate pool 仍然大量展示 `clusterId / templateHash / verifier / quality`

影响：

- 这些字段对工程定位问题有价值
- 但对外产品应优先回答：
  - 为什么这条样本被筛进来 / 被挡住
  - 是自动通过还是需要人工确认
  - 进入下游前还缺什么

### P1. Dataset 页仍偏 builder-first，而不是 lineage-first

现状：

- 页面从 builder 切入：`sft / preference / binary_rl`
- 再去看 snapshot

影响：

- 对训练和评测使用者来说，真正重要的是：
  - 哪个 cohort 生成了哪个 snapshot
  - 哪个 snapshot 进入了哪个 training request
  - 哪个 candidate 对应哪个 eval 与 handoff
- 现在需要跨多个页面才能拼出整条血缘。

### P1. Training / Eval / Handoff 仍是三个结果页，不是一个上线接替工作区

现状：

- training 看请求、候选、执行、交接
- evaluation 看 suite 和 scorecard
- coverage 看建议阶段
- handoff 看 route config 和 rollback 条件

影响：

- 用户能分别看懂每块，但仍然看不到一条连续“接替链”。
- 产品缺少一个真正的 `request -> candidate -> eval -> decision -> handoff -> rollout ack` 统一工作区。

### P1. Coverage / Handoff 还不够 launch-grade

现状：

- 已经能展示 candidate、推荐阶段和 rollback 条件。
- 但仍缺关键生产字段：
  - 目标流量范围
  - 放量百分比
  - 审批人 / 批准状态
  - router 实际执行回执
  - shadow / canary / expand 的执行时间线

影响：

- 当前更像“替代建议展示页”，还不是“模型上线接替控制台”。

### P2. 页面中仍有假交互和占位交互

现状：

- `Tabs` 当前只切按钮状态，不切真实内容。
- 一些页面表面上提供了“Manifest / 切分分布 / 记录预览 / 谱系”“指标 / 阈值 / 决策历史 / 失败分析”。
- 但用户点下去不会获得对应内容层变化。

影响：

- 这类交互在内部预览可以容忍
- 对外演示会立即被识别为半成品

### P2. 布局注意力层级仍然不理想

现状：

- 右侧 guidance 只在 `2xl` 显示
- 底部任务栏长期占据页面空间
- 大量白色卡片样式相近，视觉权重差异不足

影响：

- 中等屏宽时，用户拿不到最重要的上下文指导
- 真正高优先级的信息没有被明显提升

## 5. 改造原则

### 5.1 流程优先，对象其次

- 一级信息架构先服务完整流程
- 对象页作为流程节点的 drill-down，而不是并列替代入口

### 5.2 结论优先，证据其次

- 先回答“当前状态 / 为什么 / 下一步”
- 再展开 artifact、manifest、path、raw id

### 5.3 一条用户态状态机

建议统一成：

```text
已接入
  -> 已结构化
  -> 已判定
  -> 待复核
  -> 已冻结
  -> 已导出
  -> 训练中
  -> 评测中
  -> 可灰度
  -> 已接替
```

`E0 / E1 / E2` 和内部 stage 下沉为技术明细。

### 5.4 一页只保留一个主任务

- 每个页面只保留一个最强主 CTA
- 页面主标题下必须明确说明“这一步要做什么”

### 5.5 上线接替必须具备生产语义

`coverage / handoff` 页面不能只展示建议，还必须表达：

- 当前允许阶段
- 流量作用范围
- rollback 信号
- 审批与执行回执

## 6. 推荐信息架构

建议把顶层导航改成编号式流水线：

1. `接入`
2. `运行与轨迹`
3. `自动判断`
4. `人工筛选`
5. `数据集`
6. `训练`
7. `验证`
8. `上线接替`
9. `回流复核`

对象页作为二级导航或页内子区：

- `session / run / replay`
- `slice / cohort / snapshot`
- `training request / candidate / eval execution / handoff`

## 7. 页面改造建议

### 7.1 首页：改成 Pipeline Control Tower

首屏建议只保留：

- 一条全局 stepper
- 每个阶段的数量、阻塞和最新更新时间
- 一个“继续当前流程”的主 CTA
- 一个“查看当前最卡住任务”的次 CTA

以下内容下沉到第二屏：

- 版本边界
- 健康矩阵
- 风险流
- 机会面板

### 7.2 Access / Sessions / Replay：做成前半程连续工作区

建议：

- `接入` 页只负责接入状态、请求归属、语义覆盖、是否已经形成首条可回放 run
- `运行与轨迹` 页负责：
  - run timeline
  - trajectory gate checklist
  - eligibility 结论
  - 下一步动作

Replay 页需要新增显式卡片：

- step integrity
- branch fidelity
- semantic completeness
- auto-judge result
- dataset eligibility

### 7.3 Supervision / Curation：改成 decision-first workbench

建议：

- supervision 主视图展示：
  - 自动判断结论
  - 低置信原因
  - 人工 override 入口
- candidate pool 主视图展示：
  - 可入池
  - 待人工确认
  - 已打入 holdout
  - 每条样本被拦下的主原因

技术字段如 `targetRef / clusterId / templateHash` 全部下沉到二级面板。

### 7.4 Datasets：改成 snapshot lineage workspace

建议主列改成：

- cohort
- snapshot
- readiness / blockers
- 下游 training / eval 入口

builder 不再充当一级视角，而作为“导出模板 / 训练用途”解释信息。

### 7.5 Training / Evaluation / Handoff：整合成模型接替工作区

建议新增统一 stepper：

```text
请求
  -> 候选
  -> 评测
  -> 决策
  -> 交接
  -> 执行回执
```

每一步都应显示：

- 当前状态
- 上游输入
- 下游输出
- 负责方
- 下一步动作

### 7.6 Coverage / Handoff：升级成 launch control

必须补齐以下字段：

- 目标流量范围
- 当前放量比例
- 影子 / 灰度 / 扩量时间线
- 审批人 / 批准状态
- router ack
- 回滚监控来源
- 最近一次 guardrail 检查结果

### 7.7 Feedback：显式闭环回流

建议把反馈去向做成固定三类：

- 回到轨迹复查
- 回到自动判断
- 回到候选池 / cohort refresh

每条 feedback 必须可见：

- 来源阶段
- 触发原因
- 回流目标
- 是否已重新进入下一轮 snapshot / eval

## 8. TODO List

以下 TODO 按优先级拆分。

### P0 对外可讲清楚

- [ ] T1 重做一级导航为流程优先结构，并加入全局 stage stepper。
- [ ] T2 重做首页首屏，改成 Pipeline Control Tower，不再把“预览边界”放在首屏核心位置。
- [ ] T3 统一用户态状态机，减少 `E0 / E1 / E2 / stage / reviewStatus` 并行口径。
- [ ] T4 在 Replay 中加入明确的 trajectory gate / eligibility checklist。
- [ ] T5 让 `接入 -> 运行与轨迹 -> 自动判断 -> 人工筛选` 形成连续主路径，而不是独立对象页集合。

### P1 提升流程清晰度

- [ ] T6 把 Supervision 改成自动判断工作台，主信息层只展示结论、置信度和下一步。
- [ ] T7 把 Candidate Pool 改成人工筛选工作台，主信息层优先展示“为什么入池 / 为什么阻塞”。
- [ ] T8 把 Datasets 改成 snapshot lineage workspace，以 cohort / snapshot / downstream 为主线。
- [ ] T9 把 Training / Evaluation / Handoff 串成统一的“模型接替工作区”。
- [ ] T10 给 Coverage / Handoff 补齐 launch-grade 字段：流量范围、审批状态、router ack、回滚来源。

### P2 消除半成品感

- [ ] T11 让所有 tabs 变成真实内容切换，不再保留假交互。
- [ ] T12 调整布局优先级：让 guidance 在 `xl` 可见，后台任务栏可折叠，并减少同质白卡片。
- [ ] T13 统一外部口径文案，把“内部对象名”进一步下沉到技术明细。
- [ ] T14 为关键流程页补足真实空态、阻塞态和回退态，而不是只展示 happy path。

### P3 上线接替生产化

- [ ] T15 定义 `promotion -> handoff -> router ack -> rollback` 的完整产品状态流。
- [ ] T16 在 Web 中展示真实 rollout 执行回执，而不是只展示 promotion 推断结果。
- [ ] T17 把 feedback 重新挂回具体 snapshot / eval / coverage 决策，形成可追溯回流血缘。

## 9. 验收标准

改造完成后，产品至少应达到以下标准：

1. 新用户第一次打开首页，能在 30 秒内理解当前整体流程和所在阶段。
2. 用户在 Replay 中能直接看出一条 run 为什么能或不能进入 dataset。
3. 用户在 Dataset 中能看清 snapshot 与 training / eval / handoff 的完整血缘。
4. 用户在 Coverage / Handoff 中能看清“建议”“审批”“执行”“回滚”四类不同状态。
5. 全站不存在只切按钮状态、不切真实内容的假交互。
6. 产品可对外用“学习数据与模型接替控制面”叙事，而不需要额外口头解释每个对象页之间的关系。
