# 设计标准：评测、放量与回流

本文定义如何验证“小模型在某个任务切片上可以覆盖或替代大模型”，以及如何把结果安全放到线上。

这里的核心对象是 `eval suite`、`scorecard`、`promotion decision`，不是训练 split。

## 1. 核心原则

替代不是主观判断，而是按 slice 做的受控对照结论。

要宣称某个 slice 可被小模型覆盖，至少要满足：

- 同一个 `slice_id`
- 同一工具后端
- 同一停止条件
- 同一评测口径
- 同一风险约束

禁止用“整体平均更便宜”替代“该 slice 已满足质量门槛”。

## 2. 一等对象

| 对象 | 作用 |
| --- | --- |
| `eval suite` | 一批被固定用途和边界的评测 case |
| `scorecard` | 某次实验对某个 slice 的指标对照结果 |
| `promotion decision` | 是否允许进入下一阶段 |
| `rollout stage` | 当前放量阶段 |
| `feedback queue` | 需要回流到策展和训练的数据入口 |

## 3. 评测资产分层

评测资产必须与训练 split 分开治理。

### Frozen Offline Test

来源：

- 训练未见过的 `task_instance_key`
- 训练未见过的 `prompt template`
- 训练未见过的 `session / run`

用途：

- 核心准确率与成功率验收

### Golden Regression

来源：

- 代表性强
- 长期稳定
- 覆盖关键业务切片

用途：

- 版本间长期回归
- 关键流程不退化检查

### Shadow Traffic Suite

来源：

- 更晚时间窗口的真实流量
- 用户不可见的小模型并行执行

用途：

- 检查时间漂移
- 检查线上分布变化
- 暴露离线集看不到的问题

`golden` 和 `shadow` 都不是训练 split，也不应在 dataset snapshot 中混成 `train / val / test` 的一部分。

## 4. 默认评测指标

每个 slice 至少要比较：

| 指标 | 含义 |
| --- | --- |
| `task_success_rate` | 任务最终成功率 |
| `verifier_pass_rate` | 自动验收通过率 |
| `format_valid_rate` | 输出结构正确率 |
| `tool_success_rate` | 工具调用成功率 |
| `avg_turns` / `avg_tool_calls` | 执行效率 |
| `p50` / `p95 latency` | 时延表现 |
| `unit_cost` | 单请求成本 |
| `fallback_rate` | 回退到大模型的比例 |
| `abstain_or_uncertain_rate` | 主动放弃或低置信退出比例 |
| `safety_regression` | 风险或安全退化 |

禁止只用单一 accuracy 或单一 reward 宣告替代成功。

## 5. 默认验收门槛

每个 slice 的验收门槛必须在实验前固定，默认应包含：

1. 小模型成功率达到大模型基线的既定比例。
2. verifier 通过率不能显著回归。
3. 格式错误率和工具错误率不能明显上升。
4. `p95 latency` 或 `unit_cost` 至少有一项带来明确收益。
5. 高风险 slice 不得引入新的安全退化。
6. fallback rate 必须在 coverage policy 可接受范围内。

具体数字可以按业务调整，但不能事后为了通过而改门槛。

## 6. 验证阶段

### 阶段 A：离线对照

做法：

- 大模型与小模型跑同一批 frozen offline test
- 使用同一工具环境和 verifier
- 生成统一 scorecard

目标：

- 判断该 slice 是否具备进入 shadow 的资格

### 阶段 B：Shadow

做法：

- 线上真实请求仍由大模型返回
- 小模型并行执行但不对用户生效
- 比较两者结果、verifier 和 fallback 触发情况

目标：

- 发现分布漂移
- 发现未知 subtype
- 发现离线数据没覆盖的异常工具路径

### 阶段 C：Canary

做法：

- 只对低风险 slice 小比例放量
- 默认保持 fallback 到大模型
- 严格监控 scorecard 中的关键指标

目标：

- 检查真实业务条件下的小流量稳定性

### 阶段 D：Slice Rollout

做法：

- 按 coverage policy 对特定 slice 扩大放量
- 对未知 subtype 和高风险 case 继续保持大模型兜底

目标：

- 在受控范围内扩大覆盖，而不是追求“整体替代”

## 7. 放量与回滚策略

默认采用分层放量：

1. `0% -> offline only`
2. `0% user-visible -> shadow`
3. `1% to 5% -> canary low-risk slice`
4. `10% to 25% -> covered slice expansion`
5. `50%+ -> stable slice only`
6. `100% -> only after long-term stable scorecards`

如果任一关键指标触发回滚阈值，应立即回退到大模型。

默认回滚触发包括：

- verifier pass rate 突降
- safety regression
- fallback rate 异常抬升
- 新 subtype 大量出现
- 工具错误率显著升高
- 成本收益不再成立

## 8. 回流机制

替代验证不是终点，必须形成反馈闭环。

以下 case 必须回流：

- fallback 触发样本
- large / small disagreement 样本
- verifier fail 样本
- 新出现的 subtype
- 高成本异常样本
- 新工具路径或新失败模式

这些样本优先进入：

- session inbox 复查
- review queue 补标
- cohort refresh
- 下一轮 dataset snapshot

## 9. 输出要求

每次评测和放量决策都必须产出固定材料：

- `slice_id`
- coverage policy 版本
- 训练数据版本
- 评测资产版本
- 模型版本
- scorecard
- failure analysis
- promotion decision
- rollback condition

没有这些材料，就不应宣称“已可替代”或“已可全量”。

## 10. 当前版本的设计结论

- 评测资产和训练集必须分开治理。
- 小模型替代必须先在 `slice` 上成立，再进入放量，不允许做笼统的“整体替代”表述。
- shadow、canary、rollback、feedback queue 都应是默认流程的一部分，而不是上线后的补救措施。
