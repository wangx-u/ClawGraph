# 产品视角：ClawGraph 是什么

这篇文档面向产品、平台和训练团队，帮助你快速判断：

- ClawGraph 解决什么问题
- 它现在已经能做什么
- 用户会怎么接入和使用
- 它如何和异步训练框架配合
- 哪些能力已经落地，哪些仍属于下一步扩展

## 一句话定义

ClawGraph 是一个面向 agent 学习的执行数据层。

它不负责替代 agent runtime，也不直接负责模型训练。它负责把真实运行中的
agent 交互沉淀为可复用、可重放、可监督、可导出的执行图数据，让同一份运行
记录可以服务于：

- 回放与调试
- 样本筛选
- 打分与排序
- SFT 数据构建
- preference 数据构建
- binary RL 数据构建
- 向异步训练系统做文件级交接

## 它解决的核心问题

很多 agent 系统已经能运行，但训练阶段常见几个断层：

1. 线上有日志，但日志是平的，难以复用为训练样本。
2. agent 有重试、fallback、subagent，但这些结构通常丢失在文本日志里。
3. 调试、评估、训练各用一套数据，导致同一次运行难以复查和复用。
4. 奖励、偏好、标签通常后补，容易和原始执行记录混在一起，难以审计。
5. 下游训练系统需要的是稳定文件输入，但上游 runtime 经常只能给临时日志。

ClawGraph 的思路是把这些问题拆开处理：

- 先稳定捕获真实执行
- 再推导 branch 和 replay 视图
- 再外挂 supervision artifact
- 最后按训练目标导出 JSONL 和 manifest

## 产品定位

从产品边界看，ClawGraph 位于四层之间：

- 上游：OpenClaw 风格 runtime、OpenAI-compatible runtime、tool runtime
- 中间：执行捕获、branch 解释、artifact 管理、dataset builder
- 下游：SFT、偏好学习、binary RL、异步 RL、蒸馏、评估系统
- 外部：judge、reward service、人工标注、策略分析系统

它的角色不是“训练平台”，而是“训练就绪的数据中间层”。

## 当前已经落地的能力

### 1. Proxy-first 接入

这是当前最成熟、最容易落地的路径。

只要把模型和工具请求路由到 `clawgraph proxy`，系统就能自动记录：

- `session_id`
- `run_id`
- `request_id`
- request started
- response chunk
- response finished
- error raised

对产品来说，这意味着：

- 不需要先改动业务逻辑
- 不需要先改训练器
- 可以先获得真实流量下的 replay 和 inspect 能力

### 2. 不可变事实存储

ClawGraph 把采集到的执行记录存成 append-only facts。

这带来两个产品收益：

- 原始执行事实不会因为评分策略变化而被覆盖
- 后续 builder、judge、artifact 逻辑都可以重跑

这对回溯问题样本、审计数据来源、比较不同监督策略很重要。

### 3. Branch-aware 执行视图

ClawGraph 不只保存“发生了什么”，还尝试回答“这些动作之间是什么关系”。

当前系统已经支持：

- request span 关联
- branch 推断
- 声明式 branch 语义
- retry / fallback / subagent 类结构表达
- replay 视图
- inspect 视图

这意味着产品上可以把 agent 执行从“平日志”升级成“结构化运行图”。

### 4. 外挂 supervision artifact

ClawGraph 把监督信息和执行事实分离。

这类 artifact 可以是：

- score
- reward
- label
- preference
- ranking
- critique
- distillation target

当前内置 bootstrap 已经支持两类常用监督：

- 请求成败分数
- branch preference

这使得团队可以先采集执行，再决定如何打分和导出，而不需要在 runtime 内硬编码监督逻辑。

### 5. 内置训练数据导出

当前内置 builder 有四类：

- `facts`
- `sft`
- `preference`
- `binary_rl`

每次导出都会产出：

- 一个 `*.jsonl`
- 一个 `*.manifest.json`

这为产品化提供了稳定边界：

- 上游系统只负责产生执行和监督
- 下游系统只负责消费文件

## 当前产品逻辑

从用户路径看，ClawGraph 的完整闭环是：

1. 采集一段真实 agent 运行
2. 在 session / run / request / branch 维度上检查质量
3. 必要时补充 semantic event
4. 必要时补充或 bootstrap artifact
5. 运行 readiness 检查
6. 选择 builder 导出数据
7. 把 JSONL 与 manifest 交给训练系统

这条路径的产品含义是：

- 数据不是一采完就盲目训练
- 先 inspect，再 export
- 训练前就可以发现 branch 歧义、监督不足、样本不足

## 用户怎么使用

### 典型用户角色

最适合 ClawGraph 的用户通常有三类：

- 平台团队：希望给现有 runtime 加最小侵入的数据捕获能力
- RL 团队：希望把 agent 运行转成可训练样本
- 评估团队：希望在真实执行上做 replay、打分、排序和筛选

### 典型接入方式

#### 模式 A：透明代理

这是推荐默认路径。

用户只需要：

- 把模型请求接到 `clawgraph proxy`
- 把工具请求接到 `clawgraph proxy`

此时用户立刻得到：

- session / run / request 归档
- replay
- inspect
- readiness
- 后续导出能力

适合：

- 首次接入
- 真实流量验证
- 尽量少改 runtime 的团队

#### 模式 B：代理加稳定上下文

如果团队希望更稳地关联跨服务请求，可以显式传入：

- `x-clawgraph-session-id`
- `x-clawgraph-run-id`
- `x-clawgraph-user-id`
- `x-clawgraph-thread-id`
- `x-clawgraph-task-id`
- `x-clawgraph-parent-id`

适合：

- 多服务协同
- worker / controller 分离
- replay 对关联精度要求更高的场景

#### 模式 C：代理加语义契约

当 retry、fallback、controller routing 对训练质量很重要时，再增加 semantic event。

优先建议增加：

- `retry_declared`
- `fallback_declared`
- `branch_open_declared`
- `branch_close_declared`
- `controller_route_decided`

适合：

- 训练关键路径依赖 branch 质量
- 推断 branch 已经不够准确
- 需要更强的 preference / binary RL 样本质量

## 对产品最重要的三个使用场景

### 场景 1：先做 replay 和定位问题

用户先不关心训练，只想知道 agent 在真实运行时到底做了什么。

此时 ClawGraph 的价值是：

- 给出 session 级全貌
- 识别失败请求和重试路径
- 还原 branch 结构
- 为后续监督和训练留好原始数据

### 场景 2：把真实运行快速变成训练样本

用户已经有真实 agent 轨迹，想生成：

- SFT
- preference
- binary RL

此时 ClawGraph 的价值是：

- 不必重写 runtime
- 不必把训练逻辑塞进 runtime
- 不必让下游训练器读原始数据库

### 场景 3：把评估、监督、导出放在同一数据闭环里

同一条 run 可以先被 replay，再被打分，再被导出。

这比“日志一份、评估一份、训练一份”的三套链路更容易产品化，也更容易审计和迭代。

## 如何和异步训练框架结合

### 推荐的产品边界

当前最推荐的结合方式是“松耦合文件边界”。

也就是：

- ClawGraph 负责采集、解释、监督、导出
- 异步训练框架负责读取 JSONL 和 manifest 并训练

不要让下游训练系统反向依赖 `clawgraph.db`。

这样做的产品收益是：

- 两边职责清晰
- 升级风险低
- runtime、数据层、训练层可以独立迭代

### 当前最适合对接的异步训练任务

ClawGraph 现在最适合给异步训练框架提供三类输入：

- `sft`：用于蒸馏、监督微调、冷启动
- `preference`：用于 DPO/IPO/ORPO 类偏好优化
- `binary_rl`：用于 reward / label 驱动的离线训练、rerank、过滤

从产品角度看，这意味着它已经能支撑“异步训练数据供给层”，尤其适合：

- 数据异步生产、训练异步消费
- 多团队协同
- 训练前先做人工或自动质检

### 和在线异步 RL 的关系

如果下游框架是像 AReaL 一样的在线异步 PPO / GRPO 系统，要求的不只是文本轨迹，还包括：

- token ids
- output logprobs
- policy version
- staleness / off-policyness 控制信息

这一点上，ClawGraph 当前还没有把 token 级训练张量作为一等导出能力内置进去。

所以当前更现实的产品关系是：

- AReaL 之类系统负责在线、token 级、策略版本敏感的异步 RL
- ClawGraph 负责 branch-aware capture、监督管理、文本级训练导出

换句话说：

- 它已经适合作为异步训练的数据前置层
- 但还不是严格意义上的 token-level async PPO 数据面

### 如果要做更深一层集成

后续若要把 ClawGraph 升级为异步 RL 的更核心数据层，建议新增几类字段：

- policy version / checkpoint version
- input token ids
- output token ids
- output logprobs
- loss mask
- reward assignment 的版本和来源
- run 结束时的 episode summary

一旦这些字段成为事实或 artifact 的标准部分，ClawGraph 才能更直接地向在线异步 RL 框架输出可训练张量。

## 当前边界和限制

从产品上需要明确几件事：

1. ClawGraph 现在不是训练引擎。
2. ClawGraph 现在不是在线奖励服务。
3. ClawGraph 当前内置 builder 主要是文本级训练样本导出。
4. ClawGraph 的“async RL bridge”目前主要指稳定文件交接，而不是直接承接 token-level PPO 数据面。
5. 如果 runtime 不提供稳定上下文或语义信号，branch 解释会更依赖推断，质量也会受限。

这不是缺点，而是当前产品边界的有意设计：

- 先把 capture、inspect、export 这条链做好
- 再逐步向更深的训练耦合推进

## 适合现在推进的产品路线

如果以产品落地为目标，建议按下面顺序推进：

1. 先用透明代理验证真实运行采集是否稳定
2. 让团队先习惯用 replay / inspect 看运行质量
3. 引入 artifact bootstrap，形成第一批 SFT / preference / binary RL 数据
4. 用 JSONL + manifest 对接异步训练系统
5. 当 branch 质量成为瓶颈，再补 semantic contract
6. 当 token-level async RL 成为目标，再扩展协议和 builder

## 总结

从产品视角看，ClawGraph 当前最有价值的定位不是“另一个训练框架”，而是：

一个把真实 agent 执行稳定转化为训练资产的中间层。

它最适合解决的问题是：

- 让 runtime 采集更低侵入
- 让 replay 和训练共用一份数据事实
- 让监督后挂而不是前埋
- 让异步训练系统吃到稳定、可审计、可复用的数据文件

如果你的目标是把 agent 从“能运行”推进到“能稳定地产生训练资产”，ClawGraph 已经有明确产品价值。
