## 0. 方案摘要

[commonstack_router_design.md](attachment:b3233727-5ee5-45d0-9f94-760e5bd27aa6:commonstack_router_design.md)

### 0.1 目标

在 **企业无感** 的前提下，仅依赖 **CommonStack 可观测到的 agent 轨迹**，把当前由 **GPT-5.4** 承担的单一企业 agent 任务，逐步迁移到一个 **小尺寸 student 模型** 上，以显著降低推理成本与延迟，同时尽量保持任务成功率、工具调用准确率和输出契约不下降。

### 0.2 关键约束

- 企业侧 **不改接口、不改 agent、不参与标注**。
- 可用数据源只有 **CommonStack 的在线轨迹、提示词、工具调用、工具返回、后续用户反馈、回退信息**。
- 初始线上模型是 **GPT-5.4**。
- 最终目标是通过 CommonStack 的统一 alias / router / verifier，把 student 做成 **“企业无感平替”**。

### 0.3 一句话结论

这不是一个“单次训练小模型替代大模型”的项目，而是一个 **CommonStack 平台侧 teacher–student 替代工厂**：

1. **采集并规范化轨迹**；
2. 把轨迹切成 **可训练的 step-level 决策状态**；
3. 用 **SFT** 先学会 agent 的基本动作；
4. 用 **DPO / 偏好蒸馏** 微调 final text 与主观偏好；
5. 用 **step-level RL**（GRPO / RFT / SDPO 混合）优化工具调用、结构化输出和澄清决策；
6. 通过 **router + verifier + fallback** 渐进上线；
7. 持续从新轨迹再生数据，循环迭代 student。

---

## 1. 设计原则

### 1.1 企业无感原则

企业视角始终只看到同一个：
- 同一个 CommonStack endpoint
- 同一个 model alias
- 同一份输出 schema / tool 协议 / 错误码语义

平台内部则逐步从：
- `GPT-5.4 only`
过渡到：
- `Student first + verifier + GPT-5.4 fallback`

### 1.2 只做平台侧可证明的替代

在只有 CommonStack 轨迹的情况下，优先替代：
- 工具调用（tool call）
- 结构化 JSON 输出
- 单步检索后总结
- 需要澄清缺失字段的决策
- 风格一致但事实可验证的 final text

不把第一版目标设为：
- 多轮开放式复杂规划全替
- 高副作用写操作完全自动化
- 任意长上下文通吃

### 1.3 训练对象不是整条会话，而是“当前决策状态”

每条 agent 轨迹拆成多个 step-level 训练单元：
- `tool_call`
- `post_tool_reasoning`
- `final_json`
- `final_text`
- `clarify`
- `refuse_or_abstain`

这样做的原因：
- 数据量放大 2–5 倍
- 评测更明确
- 更容易做 verifier / reward / rollback
- 更适合 SFT、DPO、RFT、GRPO、SDPO、OPD/OPSD 这些不同训练方式复用

---

## 2. 合规与模型边界

### 2.1 默认推荐路径

如果要使用 GPT-5.4 的输出做蒸馏监督，**默认推荐 student 仍在 OpenAI 体系内**，或至少先走这一条快速上线。这样最容易直接利用：
- SFT
- DPO
- RFT
- graders / evals / trace grading

### 2.2 外部 student 的边界

如果最终 student 是 OpenAI 体系外的竞争性模型或开源模型，需要法务确认是否可以把 GPT-5.4 的输出直接用作训练监督。若不能，应改为：
- 使用企业自有输入与工具返回
- 使用程序化标签
- 使用由轨迹再生的 gold / pseudo-gold
- 使用 privileged self-distillation / self-teaching，而不是直接拿 GPT-5.4 最终答案做监督

**因此本方案在技术上给出两条实现方式：**
- **路径 A（推荐）**：OpenAI 内部 student，直接利用 GPT-5.4 教学
- **路径 B（外部 student）**：以 trace 再生标签 + 自蒸馏 + RL 为主，尽量少依赖 GPT-5.4 的直接 demo

---

## 3. 平台总体架构

```
Enterprise Agent
    -> CommonStack Unified Endpoint / Model Alias
        -> Request Serializer
        -> Pre-Router
            -> Student Model Path
            -> GPT-5.4 Teacher Path
        -> Post-Verifier
        -> Fallback Controller
        -> Response Return
        -> Trace Store
            -> Dataset Factory
            -> Evals / Trace Grading
            -> Training Pipelines (SFT / DPO / RL / Distillation)
            -> Shadow Replay / Canary Release
```

### 3.1 核心组件

### A. Request Serializer

把线上乱序 prompt / tools / retrieval / tool results 归一为统一 canonical state，保证：
- 训练看到什么，线上就喂什么
- 不同算法复用同一输入表示

### B. Trace Store

保存完整可回放轨迹：
- 最终拼装后的 messages
- tools 与 schema
- retrieval 片段或其指纹
- tool calls 与 tool results
- parser / schema / downstream success
- retry / fallback / user correction / manual override
- token / latency / cost

### C. Dataset Factory

从轨迹自动导出：
- SFT JSONL
- DPO preference pairs
- RL / RFT prompt datasets
- reward model datasets
- eval / holdout / shadow replay sets

### D. Router + Verifier + Fallback

保证 student 可以逐步替代 teacher，而企业无感。

---

## 4. 数据底座：CommonStack 必须采集什么

## 4.1 原始 trace schema（建议）

```json
{
  "tenant_id": "...",
  "agent_id": "...",
  "session_id": "...",
  "trace_id": "...",
  "turn_id": 12,
  "step_index": 3,

  "request_ts": "2026-03-18T10:00:00Z",
  "prompt_version": "...",
  "tool_schema_version": "...",
  "response_schema_version": "...",

  "messages_raw": [...],
  "tools_raw": [...],
  "response_schema": {...},
  "retrieval_context": [...],

  "model_name": "gpt-5.4",
  "assistant_output": {...},
  "tool_calls": [...],
  "tool_results": [...],

  "parser_ok": true,
  "schema_pass": true,
  "tool_exec_ok": true,
  "downstream_status": "success|fail|unknown",
  "fallback_happened": false,
  "retry_count": 0,
  "manual_override": false,
  "user_correction": false,

  "next_turns": [...],
  "input_tokens": 2100,
  "output_tokens": 190,
  "latency_ms": 1200,
  "estimated_cost": 0.02
}
```

### 4.2 缺一不可的字段

如果目前 CommonStack 没采：
- 最终拼装 prompt
- tools / tool schema
- tool result
- structured output parse status
- downstream success / fail
- retry / fallback

则必须补齐。否则后续 SFT 能做，但 RL、reward、trace eval 和 verifier 会受限。

---

## 5. 统一训练单位：Canonical State

把每个 step 归一为统一决策状态：

```json
{
  "state_id": "trace_123_turn_7_step_2",
  "slice": "tool_call",
  "visible_state": {
    "agent_contract": "...",
    "messages": [...],
    "dialogue_summary": "...",
    "retrieval_facts": [...],
    "tools": [...],
    "response_schema": {...},
    "last_tool_results": [...]
  },
  "oracle": {
    "assistant_action": {...},
    "tool_name": "get_order_status",
    "tool_args": {"order_id": "123"},
    "final_answer": null
  },
  "feedback": {
    "parser_ok": true,
    "tool_exec_ok": true,
    "downstream_success": true,
    "fallback": false,
    "user_correction": false,
    "retry_count": 0
  },
  "future_privileged": {
    "later_successful_answer": "...",
    "later_tool_results": [...],
    "resolved_slots": {...}
  }
}
```

### 5.1 visible_state 与 future_privileged 的区别

- `visible_state`：student 推理时真实可见
- `future_privileged`：只能给 teacher / self-teacher / privileged distillation 用

这一区分决定了：
- 普通 SFT / DPO / RL 只能看 `visible_state`
- OPSD / privileged self-distillation 才能利用 `future_privileged`

---

## 6. 数据工厂：如何从轨迹自动长出训练集

## 6.1 自动再生标签

### A. 成功标签

- `hard_success`：tool success + parser success + no fallback + no manual override
- `soft_success`：后续 1–2 turn 没有用户纠正 / 重试
- `hard_failure`：tool fail / schema fail / fallback / manual override / 明确纠正
- `uncertain`：其余

### B. 任务切片标签

- `tool_call`
- `post_tool_reasoning`
- `final_json`
- `final_text`
- `clarify`
- `refuse_or_abstain`

### C. 风格标签

从成功轨迹归纳：
- 长度区间
- 是否先结论
- 是否列步骤
- 是否必须简短
- 是否固定只返回 JSON

### D. grounding 标签

从 retrieval_context / tool_results 抽取当前可见事实，用于：
- reward 的 groundedness
- hallucination 检测
- verifier

## 6.2 质量分数 Q

建议给每个 step 一个统一质量分：

```
Q =
0.35 * success_signal
+ 0.20 * schema_pass
+ 0.15 * tool_exec_pass
+ 0.10 * (1 - fallback)
+ 0.10 * (1 - user_correction)
+ 0.10 * groundedness_score
```

推荐切分：
- `Q >= 0.85`：SFT 正样本
- `0.60 <= Q < 0.85`：DPO / RL / RM 候选
- `Q < 0.60`：失败池，仅做负样本、评测、对比学习

## 6.3 去重与切分规则

- 按 `session_id / trace_id` 做 train / val / test 分割，避免同会话泄漏
- 按时间切出真正的未来测试集，例如：
    - Train: 前 70%
    - Validation: 中间 15%
    - Test: 最近 15%
- 对模板高度相似的批量请求做近重复去重
- 高风险 case 单独保留为 holdout

---

## 7. 训练集、验证集、测试集设计

## 7.1 训练集类型

### 训练集 A：SFT Train

用途：教 student 学会 agent 基本动作。

来源：
- 高质量 step (`Q >= 0.85`)
- 成功 tool_call
- 成功 post_tool
- 成功 final_json / final_text
- 成功 clarify / abstain

### 训练集 B：DPO Preference Train

用途：对齐 final_text / 某些文本化 action 的偏好。

来源：
- retry 前后
- user correction 前后
- teacher vs shadow student
- 成功答案 vs hard negative

### 训练集 C：RL / RFT Prompt Train

用途：在可验证 slice 上做 sample-grade-update。

来源：
- `tool_call`
- `final_json`
- `clarify`
- 部分 grounding 强的 `final_text`

### 训练集 D：Reward Model / Judge Calibration Train

用途：训练 Bradley–Terry RM / GenRM / judge calibration。

来源：
- preference pairs
- deterministic validator + 人工抽查小金标
- GPT-5.4 critique + 后续结果确认

## 7.2 验证集

建议至少四套：

### V1：IID Validation

从同分布轨迹中切出，评估训练收敛。

### V2：Recent Validation

最近时间窗口的数据，检测真实线上泛化。

### V3：Hard Slice Validation

低频但重要：
- clarify
- 多工具候选
- 长上下文压缩
- 高风险格式输出

### V4：Canary / Pre-production Validation

直接来自 shadow replay 的真实线上样本，不参与训练。

## 7.3 测试集

- 只在 major release 前跑
- 与 train / val 完全隔离
- 覆盖高价值切片
- 最好补一小部分人工金标（即使企业不参与，也应由平台内部 QA 完成少量 high-value 标注）

---

## 8. SFT：第一阶段必须做的基线训练

SFT 的作用不是“学会所有能力”，而是先学会：
- 什么时候调工具
- 该调哪个工具
- 参数怎么填
- 何时生成 final_json / final_text
- 缺信息时先澄清
- 何时保守回答

OpenAI 官方也明确指出，SFT 用于“example inputs + known good outputs”，适合格式、语气、结构、成本优化和蒸馏。对于小模型蒸馏，官方建议先把大模型 prompt 调到满意，再把高质量结果收集下来做小模型 SFT。

## 8.1 SFT 不做整会话，而做 step-SFT

一条轨迹：
- 用户问问题
- assistant 调工具
- tool 返回
- assistant 输出 JSON

应切为至少两个样本：
1. 当前 state -> `tool_call`
2. 当前 state + tool result -> `final_json`

## 8.2 SFT 样本格式

### 样本 1：tool_call

```json
{
  "messages": [
    {
      "role": "system",
      "content": "<AGENT_CONTRACT>当前任务模式=tool_call。缺少必填字段先澄清。</AGENT_CONTRACT>"
    },
    {
      "role": "user",
      "content": "<USER_REQUEST>帮我查订单123状态</USER_REQUEST>"
    },
    {
      "role": "assistant",
      "tool_calls": [
        {
          "id": "call_1",
          "type": "function",
          "function": {
            "name": "get_order_status",
            "arguments": "{\"order_id\":\"123\"}"
          }
        }
      ]
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_order_status",
        "description": "查询订单状态",
        "parameters": {
          "type": "object",
          "properties": {
            "order_id": {"type": "string"}
          },
          "required": ["order_id"]
        }
      }
    }
  ],
  "parallel_tool_calls": false
}
```

### 样本 2：post_tool -> final_json

```json
{
  "messages": [
    {
      "role": "system",
      "content": "<AGENT_CONTRACT>当前任务模式=final_json。只返回 status, eta, next_action。</AGENT_CONTRACT>"
    },
    {
      "role": "user",
      "content": "<USER_REQUEST>帮我查订单123状态</USER_REQUEST>"
    },
    {
      "role": "assistant",
      "tool_calls": [
        {
          "id": "call_1",
          "type": "function",
          "function": {
            "name": "get_order_status",
            "arguments": "{\"order_id\":\"123\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_1",
      "content": "{\"status\":\"shipped\",\"eta\":\"2026-03-18\"}"
    },
    {
      "role": "assistant",
      "content": "{\"status\":\"已发货\",\"eta\":\"2026-03-18\",\"next_action\":\"等待签收\"}"
    }
  ],
  "tools": [],
  "parallel_tool_calls": false
}
```

### 样本 3：clarify

```json
{
  "messages": [
    {
      "role": "system",
      "content": "<AGENT_CONTRACT>当前任务模式=clarify。若缺少必填字段，先问最小澄清问题。</AGENT_CONTRACT>"
    },
    {
      "role": "user",
      "content": "<USER_REQUEST>帮我取消订单</USER_REQUEST>"
    },
    {
      "role": "assistant",
      "content": "请提供订单号，我再帮你取消。"
    }
  ],
  "tools": [],
  "parallel_tool_calls": false
}
```

## 8.3 SFT 数据筛选规则

只放入：
- `Q >= 0.85`
- 无 future leakage
- schema / tool schema 可还原
- 无人工强改写
- 不是 fallback 后抄 teacher 的错误 student 输出

## 8.4 SFT 训练顺序

建议采样比例：
- 40% `tool_call`
- 30% `post_tool_reasoning`
- 20% `final_json/final_text`
- 10% `clarify/refuse`

训练顺序：
1. 先只学 `tool_call + post_tool`
2. 再引入 `final_json / final_text`
3. 最后加入 `clarify / refuse`

## 8.5 SFT 验收指标

- `tool_name_acc`
- `tool_arg_semantic_acc`
- `schema_pass_rate`
- `grounded_final_answer_rate`
- `clarify_decision_acc`

SFT 未达标，不进入 RL。

---

## 9. 蒸馏方案总览

对于你们这个场景，“蒸馏”不应只理解为“teacher 输出拿来做 SFT”。更完整的蒸馏路线应至少包含 4 类：

1. **Response Distillation / Step-SFT**：teacher 的优质动作与输出 -> student 学习
2. **Preference Distillation**：teacher / trace 隐含的偏好信号 -> student 学习 preferred over rejected
3. **On-policy Distillation (OPD)**：student 自己 rollout，teacher 对 student rollout 做 token-level 指导
4. **Privileged Self-Distillation (OPSD-style)**：teacher 与 student 共享同一参数或近似模型，但 teacher 能看到 future trace / privileged context

## 9.1 标准蒸馏：Response Distillation

适合：
- `tool_call`
- `final_json`
- 单步摘要
- 明确的 final_text

做法：
- 用 GPT-5.4 跑通 prompt
- 只收集满足 eval / verifier 通过的结果
- 作为 SFT 正样本训练 student

这是第一阶段主力。

## 9.2 偏好蒸馏：DPO / DPKD / f-DPO

### DPO（官方可直接用）

适合：
- final_text 风格
- 主观偏好
- 品牌话术
- 说明是否清晰、礼貌、简洁

限制：
- 每个样本是 **one-turn**，preferred / non-preferred 需要是最后一个 assistant message

### DPKD（更适合 teacher-student 蒸馏）

适合：
- teacher 与 student 的偏好蒸馏
- 不只是“模仿 teacher 唯一输出”，而是提升 teacher 输出相对 student 输出的偏好概率
- 在 response distillation 基础上进一步压 student 分布

### f-DPO（解决 reverse KL 过于 mode-seeking）

适合：
- final_text / explain / clarify 等有多个合理答案的切片
- 需要在对齐与多样性之间折中

**建议：**
- `tool_call / final_json`：偏 reverse-KL 风格或 DPKD
- `final_text / clarify`：更适合 DPO 或 f-DPO

## 9.3 On-Policy Distillation（OPD）

OPD 的核心是：
- 用 **student 自己的 rollout** 作为训练分布
- teacher 在 student rollout 上给 token-level supervision

优点：
- 解决离线蒸馏的分布偏移
- 比 off-policy 只学历史 teacher 输出更贴近真实部署

缺点：
- 需要 shadow replay / on-policy sampling
- 训练成本较高

建议：
- 只对高价值切片启用
- 优先用于 `final_text` 或“序列化 action plan”
- 如果输出较长，可考虑 **prefix-only OPD**，降低训练 FLOPs

## 9.4 Privileged Self-Distillation / OPSD

适合你们的原因非常强：
- 你们手里有未来轨迹（future trace）
- 但企业不会给额外标签

于是可以构造：
- **student policy**：只看当前 `visible_state`
- **teacher policy**：额外看 `future_privileged`，例如：
- 后续成功答案
- 后续工具结果
- 后续用户纠正
- 已解析出的缺失槽位

这种训练在你们场景里非常有价值，尤其适合：
- `clarify`
- `slot filling`
- `post_tool_reasoning`
- `which tool next`

如果最终 student 是外部模型、又不方便直接蒸馏 GPT-5.4 最终答案，这条路更重要。

---

## 10. DPO：怎么做、数据长什么样

OpenAI 官方推荐的工作流是：
1. 先对 preferred responses 的子集做 SFT
2. 再从这个 SFT 模型出发做 DPO

原因：SFT 可以先建立一个更稳的初始策略，DPO 再微调主观偏好，训练更稳定。

## 10.1 DPO 数据来源

在企业不参与标注时，DPO 样本从 4 类地方自动再生：

### D1. Retry Pairs

- 第一次回答触发 retry / user follow-up
- 后一次回答成功
- 后者 preferred，前者 non-preferred

### D2. Correction Pairs

- 用户明确说“不是这个意思”“太长了”“只要 JSON”
- 纠正后版本 preferred

### D3. Teacher vs Shadow Student

- 对同一 state，teacher 输出一份，student 输出一份
- 用 preference scorer 选 preferred

### D4. Hard Negatives

从成功答案自动造负例：
- 缺字段
- 多余 unsupported claim
- 过长 / 过短
- 风格不一致
- 结构不合法

## 10.2 DPO 数据格式

```json
{
  "input": {
    "messages": [
      {
        "role": "system",
        "content": "<AGENT_CONTRACT>当前任务模式=final_text。先结论，短句，不重复问题。</AGENT_CONTRACT>"
      },
      {
        "role": "user",
        "content": "<USER_REQUEST>查订单123状态</USER_REQUEST><FACTS>{\"status\":\"shipped\",\"eta\":\"2026-03-18\"}</FACTS>"
      }
    ],
    "tools": [],
    "parallel_tool_calls": false
  },
  "preferred_output": [
    {
      "role": "assistant",
      "content": "订单123已发货，预计 2026-03-18 送达。"
    }
  ],
  "non_preferred_output": [
    {
      "role": "assistant",
      "content": "根据目前系统里面查询到的情况来看，您的订单应该已经发货了，建议您耐心等待后续物流更新。"
    }
  ]
}
```

## 10.3 Preference Scorer

给每个候选答案打一个偏好分：

```
PrefScore =
0.30 * groundedness
+ 0.25 * completeness
+ 0.20 * style_fit
+ 0.15 * brevity_fit
+ 0.10 * safety_or_policy_fit
```

只保留差值明显的 pair，例如：
- `score(preferred) - score(nonpreferred) >= 0.15`

## 10.4 DPO 使用边界

DPO 更适合：
- final_text
- 文本化后的 clarify / refusal
- 一些文本化 action decision

不建议把核心 `tool_call` 主要交给 DPO；`tool_call` 应主要由 SFT + RL 解决。

---

## 11. RL 总体原则：只做 step-level，不做第一版 full episode

在只有 CommonStack 轨迹的情况下，第一版 RL 不应做整条 agent episode，原因：
- student 可能走到 teacher 历史中不存在的分支
- 许多工具带副作用
- 无法可靠构造全环境 counterfactual

**因此建议只做 step-level RL：**
给定一个当前 state，只优化“下一步动作”的策略。

适合进 RL 的切片：
- `tool_call`
- `final_json`
- `clarify`
- grounding 强、可验证的 `final_text`

不适合第一版进 RL 的：
- 高副作用写操作
- 强开放式多轮规划
- 纯闲聊风格任务

---

## 12. Reward 设计：必须分层，不能只靠一个 LLM judge

最稳的 reward 体系是 4 层：

1. **确定性 reward**：规则 / schema / tool / downstream success
2. **偏好型 reward model**：pairwise BT-RM / pairwise scorer
3. **生成式 reward / verifier**：GenRM / Generative Verifier
4. **LLM judge**：补代码难写的软指标

### 12.1 总 reward 模板

```
R = w_det * r_det
  + w_rm  * r_rm
  + w_j   * r_judge
  - w_c   * r_cost
```

建议初始权重：
- `tool_call / final_json`：`w_det=0.75, w_rm=0.15, w_j=0.10`
- `final_text / explain`：`w_det=0.45, w_rm=0.30, w_j=0.20, w_c=0.05`
- `clarify / refuse`：`w_det=0.55, w_rm=0.20, w_j=0.20, w_c=0.05`

并加两个硬门：
- schema 不合法 -> `R=0`
- safety / policy fail -> `R=0`

## 12.2 tool_call reward

```
r_tool = clip(
  0.35 * tool_name_exact +
  0.25 * args_semantic_f1 +
  0.15 * required_slots_present +
  0.10 * clarify_if_missing +
  0.10 * json_valid +
  0.05 * tool_count_ok -
  0.20 * hallucinated_or_invalid_arg,
0, 1)
```

说明：
- `tool_name_exact`：工具名是否正确
- `args_semantic_f1`：参数字段级或语义级 F1
- `required_slots_present`：必填字段是否齐全
- `clarify_if_missing`：缺字段时是否先澄清
- `tool_count_ok`：并行/串行数量是否合理
- `hallucinated_or_invalid_arg`：瞎填参数 / 非法 JSON

## 12.3 final_json reward

```
r_json = clip(
  0.25 * schema_pass +
  0.25 * key_field_match +
  0.20 * groundedness +
  0.15 * completeness +
  0.10 * no_hallucination +
  0.05 * brevity_fit,
0, 1)
```

## 12.4 clarify reward

```
r_clarify = clip(
  0.45 * decision_correct +
  0.25 * slot_targeting +
  0.15 * minimal_question +
  0.15 * tone_fit,
0, 1)
```

## 12.5 final_text reward

```
r_text = clip(
  0.20 * groundedness +
  0.20 * completeness +
  0.20 * style_fit +
  0.15 * brevity_fit +
  0.15 * directness +
  0.10 * no_hallucination,
0, 1)
```

### 12.6 Reward 的具体来源

### 层 1：确定性验证器（主力）

由 CommonStack 实现：
- JSON schema 验证
- field match
- tool name / args checker
- downstream API success
- parser error

### 层 2：Pairwise RM（可选但推荐）

来源：
- retry 前后
- correction 前后
- teacher vs student
- success vs hard negative

用途：
- 更稳地表达风格 / 解释质量 / 用户体验偏好

### 层 3：生成式 reward / verifier（高级可选）

适合：
- `final_text`
- 长解释
- 需要 reasoning 才能判断的 groundedness

### 层 4：LLM judge（最后补洞）

只用于：
- 难以写规则的 style / clarity / policy fit
- 需要整体语义判断的 case

用法：
- 固定 rubric
- 双顺序 pairwise 评估，降低位置偏差
- 与 deterministic / RM 分歧过大时，不参与 RL 更新，只进人工 spot-check

## 12.7 防 reward hacking

- 多 grader 组合，不让单一指标主导
- grader 与 policy 分离
- 使用验证集 `valid_reward_mean` 观察泛化
- 周期性人工抽样复核
- 对 downstream success 强加硬约束
- 对 reasoning token、长度、无意义重复加惩罚

---

## 13. RL 方法 1：GRPO / 官方 RFT 风格

### 13.1 什么时候用

适合：
- 任务有明确可验证目标
- 模型已具备一定成功率
- 希望优化工具调用、结构化输出、clarify 决策

### 13.2 数据格式（概念上）

```json
{
  "messages": [...],
  "tools": [...],
  "slice": "tool_call",
  "gold_tool_name": "get_order_status",
  "gold_tool_args": {"order_id": "123"},
  "needs_clarification": false
}
```

或：

```json
{
  "messages": [...],
  "slice": "final_json",
  "reference_facts": {
    "status": "shipped",
    "eta": "2026-03-18"
  },
  "required_fields": ["status", "eta", "next_action"]
}
```

### 13.3 训练逻辑

对每个 state：
1. 采样 `G` 个 student 候选动作
2. 用 reward stack 打分
3. 在组内做 advantage normalization
4. 做策略更新 + KL 正则到 reference policy（通常是 SFT 模型）

### 13.4 优点

- 工程实现相对成熟
- 可直接复用 RFT / RLVR / GRPO 思路
- 对 tool_call / final_json 很有效

### 13.5 局限

- 只有 terminal scalar reward 时 credit assignment 差
- 对长输出和复杂解释不够密集
- 若只有离线历史轨迹而没有 shadow replay，则是真正 RL 的条件不足

---

## 14. RL 方法 2：SDPO（Reinforcement Learning via Self-Distillation）

SDPO 适用于 **rich feedback** 场景：环境不只给一个分数，还能给：
- judge evaluation
- runtime error
- 执行失败原因
- 成功 sibling rollout

其核心不是外部 teacher，而是：
- **当前模型在看到反馈（gpt-5.4提供）后，作为 self-teacher**
- 再把反馈条件下的 token-level 分布蒸馏回原 policy

### 14.1 为什么适合你们

CommonStack 在 agent 场景中天然就有 rich feedback：
- 工具报错
- schema 失败原因
- user correction
- fallback 原因
- shadow group 中的成功样本

这正好符合 SDPO 的 rich feedback 假设。

### 14.2 但要注意一件事

**严格 SDPO 是 on-policy 的。**
如果 CommonStack 只能拿历史静态轨迹，不能让当前 student 在 shadow 模式下对同一 state 采样新动作并拿反馈，就不能做真正意义上的 SDPO，只能做离线近似。

### 14.3 GPT-5.4 在 SDPO 里的正确角色

推荐：**GPT-5.4 主要做 feedback generator / judge，不直接取代 self-teacher。**

也就是说：
- GPT-5.4 负责产出结构化 critique / rich feedback
- self-teacher 仍然是 `q(x, f)`，即看到反馈后的当前模型 / EMA teacher

这样仍然保留 SDPO 的本质。

### 14.4 GPT-5.4 feedback JSON 协议（建议）

```json
{
  "error_tags": ["wrong_tool", "missing_required_arg"],
  "tool_feedback": {
    "correct_tool": "get_order_status",
    "arg_patch": {"order_id": "123"},
    "why_wrong": "当前任务是查状态，不是取消订单"
  },
  "output_feedback": {
    "missing_fields": ["eta"],
    "hallucinated_claims": ["包裹已签收"]
  },
  "minimal_fix_hint": "使用 get_order_status，并包含 order_id。",
  "confidence": 0.91,
  "can_use_as_demo": false
}
```

### 14.5 为什么不用 GPT-5.4 直接给完整答案作为主信号

- 这样更像外部 teacher distillation，而不是 SDPO
- 反馈式训练比直接灌答案更保留探索空间
- 成本更低
- 更贴合 rich feedback 场景

### 14.6 SDPO 的训练形式

对每个 state 的每个 sampled action：
- 获得反馈 `f`
- 用 self-teacher / EMA teacher 计算 feedback-conditioned 分布
- 把该分布蒸馏到原 policy

实操上，优势信号可写成 feedback-conditioned 的 token-level dense advantage。

### 14.7 适用切片

- `tool_call`（参数细修）
- `final_json`（字段边界、格式细修）
- `clarify`（问什么、问多长）
- grounding 强的 `final_text`

---

## 15. RL 方法 3：GRPO 与 SDPO 的结合

这是你们场景里最值得考虑的高级主线。

### 15.1 为什么要结合

- **GRPO / RFT**：更接近“最大化标量 reward”，全局目标更清楚，但 credit signal 稀疏
- **SDPO**：能利用 rich feedback 做 dense token-level 修正，局部 credit 更好，但有偏且依赖反馈质量

两者结合后：
- GRPO 保持全局方向
- SDPO 修正局部 token / field / argument 错误

### 15.2 混合优势函数

```
A_mix = λ * A_GRPO + (1 - λ) * A_SDPO
```

其中：
- `A_GRPO`：组内相对奖励 advantage
- `A_SDPO`：feedback-conditioned dense advantage

### 15.3 推荐的 λ 日程

### 阶段 1：GRPO-heavy

student 还弱、反馈噪声大时：
- `λ = 0.7 ~ 0.9`

### 阶段 2：Balanced

student 已具备一定成功率：
- `λ = 0.4 ~ 0.6`

### 阶段 3：SDPO-heavy

rich feedback 稳定后：
- `λ = 0.1 ~ 0.3`

### 15.4 分 slice 调 λ

- `tool_call / final_json`：更偏 GRPO + deterministic reward
- `clarify / final_text`：更适合 balanced 或 SDPO-heavy

### 15.5 什么时候不建议混合

- 反馈极不稳定
- student 成功率仍接近 0
- 无法 shadow replay
- 切片 reward 不可验证

---

## 16. RL 方法 4：OPD / Prefix-OPD（可选高级增强）

OPD 的核心：
- student 生成自己的 rollout
- teacher 在这些 rollout 上做 token-level distillation

### 16.1 适合什么

- 长 final_text
- 复杂 reasoning 风格
- 需要纠正 student 自己会跑偏的长序列输出

### 16.2 为什么不是第一优先级

- 训练成本高
- 需要在线 teacher
- 对 tool_call 这种短动作，GRPO/SDPO 已经更直接

### 16.3 Prefix-OPD 什么时候值得用

如果：
- final_text 很长
- teacher 成本高
- 训练信号集中在开头若干 token

则只蒸馏前缀，比 full OPD 更省。

---

## 17. 统一训练路线（推荐版）

下面给出 **最落地** 的主路线。

## 17.1 Phase 0：Teacher 固化与日志采集

- 用 GPT-5.4 跑通 agent
- 固定 prompt / schema / tool contract
- 补齐 CommonStack trace 采集
- 建立 baseline eval

输出：
- 完整 trace store
- baseline 指标
- canonical serializer

## 17.2 Phase 1：Step-SFT 冷启动

- 用高质量 step 训练 student
- 先只替高频、低风险、强结构化 slice

输出：
- student-SFT-v1

## 17.3 Phase 2：DPO / Preference Distillation

- final_text 上做 DPO
- 如需更强 teacher-student 蒸馏，可用 DPKD / f-DPO（自建路线）

输出：
- student-SFT-DPO-v2

## 17.4 Phase 3：Step-level RL（GRPO / RFT）

- `tool_call / final_json / clarify` 进入 RL
- reward 以 deterministic validators 为主

输出：
- student-RL-v3

## 17.5 Phase 4：SDPO / GRPO 混合

- 在 shadow replay 环境中运行
- GPT-5.4 产出 critique / rich feedback
- 反馈条件下做 self-distillation

输出：
- student-SDPO-GRPO-v4

## 17.6 Phase 5：OPSD / Privileged Self-Distillation（可选）

- 把 future trace 作为 privileged context
- 进一步压 teacher 依赖
- 适合长期路线或外部 student

输出：
- student-final-v5

---

## 18. 推荐的主线与备选线

## 18.1 主线（最推荐）

**SFT -> final-text DPO -> step-RL（GRPO / RFT）-> selective SDPO+GRPO**

原因：
- 风险最低
- 工程上最可控
- 与 agent 任务结构最匹配
- 最容易实现企业无感替代

## 18.2 高级增强线

**SFT -> DPKD / f-DPO -> SDPO+GRPO -> prefix-OPD**

适合：
- 自建训练栈较成熟
- 追求更高 token efficiency
- 希望降低对 GPT-5.4 full-demo 的依赖

## 18.3 外部 student 线

**SFT（以 trace 再生标签为主）-> OPSD / privileged distillation -> RL**

适合：
- 不能直接用 GPT-5.4 最终答案监督
- 更依赖 trace 和自蒸馏

---

## 19. 实现平替迁移：如何企业无感上线

## 19.1 线上路由策略

### Pre-Router

请求进入时先判断：
- 是否命中已覆盖切片
- 上下文长度是否在 student 能力边界内
- 当前工具集合是否在 student 训练分布内
- 是否属于高风险任务

命中则走 student，否则走 GPT-5.4。

### Post-Verifier

student 输出后再检查：
- schema 是否通过
- tool name / args 是否合理
- groundedness 是否过线
- 是否违反 policy / safety

不过线则立即 fallback 到 GPT-5.4。

## 19.2 发布流程

### 阶段 1：Shadow Mode

- student 只旁路出结果
- 不对企业生效
- 记录 teacher vs student 对比

### 阶段 2：Canary

- 5% 流量
- 只放低风险、高频切片

### 阶段 3：Progressive Rollout

- 逐切片扩大覆盖
- 增加 tool_call、final_json、clarify

### 阶段 4：Student-first

- student 成为默认路径
- teacher 作为 verifier-fail fallback

### 阶段 5：Selective Teacher

- 仅在高风险 / 未覆盖 slice 上调用 GPT-5.4

## 19.3 企业无感的 4 个保证

1. **接口不变**
2. **模型名 / alias 不变**
3. **输出契约不变**
4. **异常自动回 teacher**

---

## 20. 评测体系：上线前后必须持续跑

## 20.1 离线核心指标

- `task_success_rate`
- `tool_name_acc`
- `tool_arg_semantic_acc`
- `schema_pass_rate`
- `groundedness_pass_rate`
- `clarify_decision_acc`
- `fallback_rate`
- `cost_per_successful_task`
- `p95_latency`

## 20.2 Trace-level 指标

- 哪一步出错
- 是否选错工具
- 是否参数缺失
- 是否因为上下文压缩导致错误
- 是否 reward hacking

## 20.3 上线门槛（建议）

student 要替代 teacher，至少满足：
- 成功率相对 teacher 不下降超过可接受阈值
- schema pass ≥ 99%
- tool name accuracy 达业务阈值
- high-risk holdout 不退化
- cost per successful task 明显下降
- p95 latency 明显改善

---

## 21. 关键工程细节

## 21.1 Tool Sandbox

为了做 shadow RL / verifier：
- 读操作工具可以直接回放或沙箱执行
- 写操作工具要么禁用 RL，要么用模拟器 / dry-run

## 21.2 Context Distiller

小模型往往不是“不会做任务”，而是“吃不下 teacher 那么长的上下文”。
因此 CommonStack 需要一个上下文压缩器：
- 压历史会话成结构化 state
- 压 tool 输出成关键字段摘要
- 检索只保留 top-k 证据块

student 学的是压缩后的决策任务，而不是直接复制 GPT-5.4 的长上下文工作方式。

## 21.3 Student Model 组织方式

建议不要“一个 student 打天下”，而是：
- 一个 shared small backbone
- 多个 adapter / head / routing policy：
- 企业/领域 adapter
- tool_call adapter
- final_json adapter
- final_text adapter

这样更容易做渐进替代。

---

## 22. 何时用哪种方法：决策表

| 目标 | 首选 | 次选 | 不建议主用 |
| --- | --- | --- | --- |
| 学会工具调用 | Step-SFT | GRPO/RFT | 纯 DPO |
| 学会结构化 JSON | Step-SFT | GRPO/RFT | 纯 DPO |
| 对齐 final_text 风格 | DPO | f-DPO / DPKD | 纯 RL |
| 细修参数 / 字段边界 | GRPO/RFT | SDPO | 纯 DPO |
| 利用 rich feedback | SDPO | SDPO+GRPO | 只做终局标量 reward |
| 利用 future trace | OPSD / privileged distillation | SDPO | 纯离线 teacher SFT |
| 纠正长输出分布偏移 | OPD / prefix-OPD | SDPO | 纯离线 SFT |

---

## 23. 最终推荐方案（给工程团队的版本）

### 23.1 方案主干

**推荐主干：**

1. **CommonStack 补齐 trace 与 canonical state**
2. **先用 GPT-5.4 作为 teacher 持续采样与打基线**
3. **step-SFT 训练 student v1**
4. **对 final_text 做 DPO（若自建可用 DPKD/f-DPO）得到 v2**
5. **对 tool_call / final_json / clarify 做 step-level RL（GRPO/RFT）得到 v3**
6. **在 shadow replay 上引入 GPT-5.4 critique，做 SDPO+GRPO 混合得到 v4**
7. **高价值难切片再加 prefix-OPD 或 OPSD 作为高级增强**
8. **通过 router + verifier + fallback 逐步替代 GPT-5.4**

### 23.2 为什么这是最优平衡

- 只依赖 CommonStack 轨迹即可落地
- 企业不需要参与标注
- teacher 与 student 可并存，支持无感切换
- SFT / DPO / RL / SDPO 各自负责最擅长的部分
- 可逐步吃掉高频高成本切片，ROI 最快显现

---

## 24. 如果只能做一版 MVP，应该怎么选

若你们只能做一版 MVP，不要一上来做最复杂的 SDPO / OPD。应当按以下最短路径落地：

### MVP 路线

1. 建立 trace schema + eval
2. 做 step-SFT
3. 做 final_text DPO
4. 对 `tool_call + final_json + clarify` 加 deterministic verifier
5. shadow + canary + fallback
6. 达到替代门槛后，再上 RL

### 为什么

- 这是最短的“先替代、再增强”的路径
- 可最快证明成本收益
- 为后续 SDPO / GRPO / OPSD 预留统一数据底座

---

## 25. 风险与缓解

### 风险 1：只有静态历史轨迹，无法做真正 on-policy RL

缓解：
- 先做 SFT / DPO
- 尽快补 shadow replay
- 先在无副作用 slice 上做 on-policy sampling

### 风险 2：reward hacking

缓解：
- 多 grader
- 验证集监控
- trace grading
- 人工 spot-check

### 风险 3：student 上下文不足

缓解：
- context distiller
- step-level state design
- prefix summarization

### 风险 4：风格学到了，事实没学到

缓解：
- groundedness hard gate
- retrieval/tool result 引用校验
- hallucination penalty

### 风险 5：外部 student 合规风险

缓解：
- 先走 OpenAI 内部 student
- 或改用 trace 再生标签 / privileged self-distillation
- 让法务确认 teacher 输出的使用边界

---

## 26. 最终结论

在“**企业无感、只能通过 CommonStack 获得数据、当前线上模型是 GPT-5.4、最终要训练一个小尺寸平替模型**”这个前提下，最稳且最能落地的完整方案是：

### 核心结论

- **数据底座**：把 CommonStack 轨迹统一成 canonical step-level state
- **训练集**：从轨迹自动再生 SFT、DPO、RL、RM 四类数据集
- **蒸馏主线**：先做 step-SFT，再做 DPO / 偏好蒸馏
- **RL 主线**：以 step-level GRPO / RFT 为主
- **高级增强**：在 rich feedback 场景下加入 SDPO；在 privileged future trace 场景下加入 OPSD；在长输出上选择性使用 prefix-OPD
- **reward 设计**：确定性规则为主，RM / GenRM 为辅，LLM judge 最后补洞
- **平替迁移**：通过 router + verifier + fallback 渐进发布，实现企业无感迁移

### 一句话版推荐

**先把 CommonStack 变成“轨迹 -> 训练集 -> eval -> rollout -> router”的训练工厂，再让 SFT、DPO、GRPO、SDPO 各做自己最擅长的部分。**

这套方案不是只押注某个算法，而是建立一个 **能持续吞日志、持续训练、持续扩覆盖率** 的平台化替代系统。

---

## 27. 参考资料

### OpenAI 官方文档

1. Supervised fine-tuning: https://developers.openai.com/api/docs/guides/supervised-fine-tuning
2. Direct preference optimization: https://developers.openai.com/api/docs/guides/direct-preference-optimization
3. Reinforcement fine-tuning: https://developers.openai.com/api/docs/guides/reinforcement-fine-tuning
4. Graders: https://developers.openai.com/api/docs/guides/graders
5. Agent evals: https://developers.openai.com/api/docs/guides/agent-evals
6. Trace grading: https://developers.openai.com/api/docs/guides/trace-grading
7. Evaluation best practices: https://developers.openai.com/api/docs/guides/evaluation-best-practices
8. Fine-tuning best practices: https://developers.openai.com/api/docs/guides/fine-tuning-best-practices
9. Model selection: https://developers.openai.com/api/docs/guides/model-selection
10. Latency optimization: https://developers.openai.com/api/docs/guides/latency-optimization
11. Services Agreement: https://openai.com/policies/services-agreement/

### OpenAI Cookbook / 资源

1. Leveraging model distillation to fine-tune a model: https://developers.openai.com/cookbook/examples/leveraging_model_distillation_to_fine-tune_a_model
2. Fine-Tuning Techniques - Choosing Between SFT, DPO, and RFT: https://developers.openai.com/cookbook/examples/fine_tuning_direct_preference_optimization_guide

### 关键论文

1. Reinforcement Learning via Self-Distillation (SDPO): https://arxiv.org/abs/2601.20802
2. DeepSeekMath (GRPO): https://arxiv.org/abs/2402.03300
3. Direct Preference Knowledge Distillation (DPKD): https://arxiv.org/abs/2406.19774
4. f-DPO: https://arxiv.org/abs/2309.16240
5. Self-Distilled Reasoner / OPSD: https://arxiv.org/abs/2601.18734
6. Fast and Effective On-policy Distillation from Reasoning Prefixes: https://arxiv.org/abs/2602.15260
7. Generative Verifiers: https://arxiv.org/abs/2408.15240
8. Generative Reward Models: https://arxiv.org/abs/2410.12832
