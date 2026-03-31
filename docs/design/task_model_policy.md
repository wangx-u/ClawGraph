# 设计标准：任务切片覆盖、训练配方与路由策略

本文定义什么样的任务切片适合什么训练配方、模型带宽和线上覆盖策略。

这里的核心对象不是“模型”，而是 `slice`。

## 1. 核心原则

正确顺序必须是：

1. 先定义稳定的 task slice
2. 再判断该 slice 的训练配方
3. 再判断覆盖它需要多大模型
4. 最后定义 route policy 和 fallback

禁止先选一个模型，再事后把各种任务硬塞进去解释。

## 2. 一等对象

| 对象 | 作用 |
| --- | --- |
| `slice` | 一个稳定、可命名、可评测的任务切片 |
| `coverage policy` | 规定某个 slice 是否允许小模型覆盖 |
| `training recipe` | 规定该 slice 用 SFT、preference、binary RL 还是蒸馏 |
| `risk tier` | 规定上线风险、fallback 和人工审查门槛 |
| `route policy` | 规定请求如何被分配到小模型或大模型 |

一个成熟系统里，coverage policy 应以 registry 形式存在，而不是写在零散脚本里。

## 3. slice 评估维度

每个 slice 至少按以下维度打标签：

| 维度 | 问题 |
| --- | --- |
| 可验证性 | 是否存在稳定自动验收 |
| 任务边界 | 输入、输出、终止条件是否清晰 |
| 决策深度 | 是否需要长链路规划 |
| 分支复杂度 | 是否常出现 retry、repair、fallback |
| 工具依赖 | 成败是否主要由工具调用决定 |
| 上下文压力 | 是否依赖长上下文 |
| 歧义度 | 是否存在多种都合理的输出 |
| 风险级别 | 错误代价是否高 |
| 成本敏感度 | 降本增效是否有明确业务价值 |

这些维度应在 slice registry 中显式保存，而不是只体现在文档描述里。

## 4. 默认切片分层

### T0：局部确定性任务

例子：

- 抽取
- 分类
- 结构化改写
- JSON 填充
- 简短模板回复

特点：

- 强约束
- 易验证
- 低上下文压力
- 低分支复杂度

建议：

- 优先小模型覆盖
- 优先 `SFT + binary RL`

### T1：单步工具使用任务

例子：

- 工具选择
- 参数填充
- 单次 API 查询后的受限回答

特点：

- 需要工具接口理解
- 仍然具备较强自动验收空间

建议：

- 小模型优先试覆盖
- 用 `SFT` 打底，再做 request 级 `binary RL`

### T2：短链路工作流任务

例子：

- 2 到 5 步工具链路
- 有固定目标的短规划任务
- 结构化业务流程

特点：

- 有一定分支
- 中间步骤和终局结果都重要

建议：

- 用 `SFT + preference + binary RL`
- 必须要求较完整的 semantic events
- 只在 slice 边界清晰时进入替代候选

### T3：长链路 agent 任务

例子：

- 多轮研究
- 多分支修复
- 长时上下文协同

特点：

- credit assignment 困难
- 奖励稀疏
- 失败归因复杂

建议：

- 默认仍由较大模型承担
- 只抽其中可验证子任务做覆盖
- 不应把整任务直接当作首批小模型 RL 目标

### T4：开放式高歧义任务

例子：

- 开放式创作
- 无唯一标准答案的复杂分析

建议：

- 不作为 binary RL 主目标
- 更适合 `SFT + preference` 或人工评估驱动蒸馏

## 5. 训练配方映射

默认映射如下：

| 条件 | 推荐配方 |
| --- | --- |
| 有单一正确答案，验证便宜 | `SFT + binary RL` |
| 有可比较分支，但难以给绝对分数 | `SFT + preference` |
| 任务较长，但局部步骤可验证 | 先拆成子 slice，再分别训练 |
| 主要依赖风格或主观偏好 | `SFT + preference` |

如果某个 slice 无法稳定解释 reward 来源，就不应纳入 RL 配方。

## 6. 覆盖策略标准

每个 slice 都应形成一条 coverage policy，至少包含：

- `slice_id`
- taxonomy 版本
- 推荐 sample unit
- 允许的 dataset family
- 最低 evidence level
- verifier 契约
- 推荐模型带宽
- 风险级别
- fallback 触发条件
- 是否允许上线覆盖
- owner 和评审责任人

没有 coverage policy 的 slice，不应进入小模型替代放量。

## 7. 线上路由标准

默认路由应采用 `small-first with guarded fallback`：

1. 请求先被分类到 `slice_id`。
2. 若该 slice 存在 active coverage policy，则优先尝试小模型。
3. 若任何风险信号超阈值，则立即回退到大模型。

默认 fallback 触发条件包括：

- `slice_id` 未知或分类置信度不足
- 风险级别过高
- 上下文长度超阈值
- 预计工具步数超阈值
- verifier 连续失败
- 输出格式错误
- 小模型置信度过低
- 新出现的 subtype 未被 coverage policy 覆盖

## 8. 模型带宽建议

| 任务层级 | 推荐模型带宽 | 推荐训练方式 |
| --- | --- | --- |
| T0 | 1.5B 到 3B | SFT, binary RL |
| T1 | 1.5B 到 3B，必要时 3B 到 7B | SFT, binary RL |
| T2 | 3B 到 7B | SFT, preference, binary RL |
| T3 | 7B 以上或保持大模型 | distill, selective RL |
| T4 | 大模型优先 | SFT, preference |

这里只是 coverage 起点，不是硬限制。

真正路由时还要结合：

- 上下文长度
- 工具数
- 错误代价
- latency / cost SLA

## 9. 当前版本的设计结论

- 模型选择必须从 slice 出发，而不是从模型出发。
- 首批小模型覆盖应集中在 T0、T1，谨慎扩到 T2。
- T3、T4 更适合保留给大模型，或只抽其中可验证子任务做局部替代。
- coverage policy 必须成为一等对象，否则评测和放量无法稳定闭环。
