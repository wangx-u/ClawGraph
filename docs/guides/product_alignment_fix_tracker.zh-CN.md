# 产品对齐修复任务清单

本文记录当前产品文档、设计、代码和 UI 对齐修复的执行清单。

当前状态（2026-04-16）：

- T1 已完成：训练资产 read model、导航、搜索和 `/training` 页面已落地
- T1 补充完成：训练资产详情页与 manifest-backed registry CLI 已落地
- T2 已完成：Coverage 页面只展示真实字段和 rollback 条件
- T3 已完成：supervision / curation candidates / evaluation 深页的 raw id 已降级
- T4 已完成：`clawgraph logits doctor` 与显式环境变量约定已落地
- T5 已完成：设计总览、PRD、rollout 与 Logits 设计文档已统一现状口径
- T6 已完成：后端单测、前端 typecheck/build、浏览器 e2e 全部通过
- T7 已完成：首方远端 HTTP bundle / mutation API 已内建，远端模式可执行人工复核
- T8 已完成：训练资产已写入 store，并由 store-backed registry 统一读取
- T9 已完成：training 深页主视图已降噪，路径和 JSON 下沉到技术明细
- T10 已完成：Web/API contract、README、设计文档已对齐首方 API 与 store-backed registry
- T11 已完成：发布与运行契约已补充 optional dependency、安装说明与能力边界
- T12 已完成：独立 Python control-plane 服务已落地，Dashboard/Training 主路径不再要求 Next 每次 shell 到本地 Python
- T13 已完成：训练工作台已支持提交训练、发起评测、生成交接，不再只停留在观察态
- T14 已完成：feedback mutation 已改成服务端 actor 绑定，前端不再传 reviewer 作为可信身份
- T15 已完成：Logits workspace auto-discovery 改为显式 opt-in，默认优先安装包或显式路径
- T16 已完成：补充首方 API 的 auth/load smoke 入口与 control-plane HTTP 回归测试

## P1

### T1 训练资产进入产品面

问题：

- 文档已经把 Dashboard 定位成“训练资产运营台”
- 真实产品面仍主要停留在数据治理、评测和反馈
- `training request / model candidate / eval execution / router handoff` 缺少统一 read model 和页面入口

交付：

- 训练资产读模型进入 dashboard bundle
- Web 增加训练资产入口和详情摘要
- 搜索、导航和底部任务栏能够读取真实训练资产

验收：

- 用户能从 Web 中看到训练请求、候选模型、评测执行和路由交接
- 训练资产不再只存在于磁盘 manifest 或 CLI 输出

### T2 Coverage 语义收紧为真实字段和建议字段

问题：

- `modelBand` 实际展示的是 candidate model
- `rollout` 实际展示的是 promotion 推断结果，不是 router 执行状态
- 护栏条件仍是静态示例文本

交付：

- Coverage 行区分“候选模型 / 建议阶段 / 当前决策”
- 护栏区域只展示真实 rollback 条件或明确空态
- 页面文案与字段语义一致

验收：

- Coverage 页面不再把推断值当成真实执行状态
- 不再展示固定示例护栏

### T3 深页去 operator-first

问题：

- supervision、candidates、evaluation 等深页仍以 raw id、targetRef、hash 为主

交付：

- 主信息层改为任务标题、业务摘要、结论和下一步
- raw id、hash、targetRef 下沉为技术明细

验收：

- 非工程用户打开深页时，先看到“这是什么 / 当前状态 / 下一步”

### T4 Logits 运行契约显式化

问题：

- 当前集成依赖 sibling repo 自动探测，缺少显式环境检查

交付：

- `clawgraph logits doctor`
- 显式环境变量/路径约定
- CLI 参考和手册更新

验收：

- 用户可以在提交训练前确认 `logits / logits-cookbook / tinker` 是否可用

## P2

### T5 设计与现状文档统一

问题：

- `design/index`、phase rollout、dashboard PRD 对“已实现 / 待实现”的表述不一致

交付：

- 统一“当前已实现 / 目标能力 / 过渡态能力”三层口径

验收：

- 用户阅读主设计文档时不会误判当前产品能力边界

### T6 回归补齐

交付：

- 后端 bundle / CLI / integration 回归
- 前端 typecheck / build / e2e 或最小页面回归

验收：

- 新增训练资产控制面和 Coverage 语义调整没有破坏现有页面

## 新一轮市场化修复

### T7 首方远端 HTTP API

问题：

- 当前 Web 没有内建 `route.ts` API
- 远端模式只能读取 bundle，不能在产品内完成人工复核
- 数据读取和 mutation 仍依赖外部 API 或本地脚本例外

交付：

- Web 内建 `GET /dashboard/bundle`
- Web 内建 feedback mutation endpoint
- `remote-http` 与 `local-store` 使用同一套产品能力开关

验收：

- 远端部署时只要 Web 有 store 访问能力，就能通过 HTTP 完成 bundle 读取与复核动作
- `/feedback` 不再因为 `remote-http` 被强制降级为只读

### T8 Store-Backed Training Registry

问题：

- 训练资产链路仍主要依赖 manifest 目录扫描
- 训练请求、候选、评测执行、交接包还不是 store 内的一等持久对象

交付：

- 训练资产写入 store
- query service 和 dashboard bundle 直接从 store 读取训练 registry
- manifest 目录只作为兼容导入/补充来源，不再是唯一真相

验收：

- 新生成的 training request / candidate / eval execution / handoff 能直接从 store 查询
- Web 和 CLI 即使没有 manifest 目录，也能展示训练血缘

### T9 Training 深页降噪

问题：

- 训练详情页主视图仍然大量展示 input/log/manifest path 和原始 JSON

交付：

- 主视图只保留业务摘要、输入资产、评测结论、交接状态、下一步
- path / manifest / route config JSON 下沉到“技术明细”

验收：

- 非工程用户能快速看懂“这是什么、当前结果、是否可替换”

### T10 Web/API Contract 对齐

问题：

- `web/docs/api-contract.zh-CN.md` 仍停留在旧 bundle 结构
- 训练资产页面和 mutation contract 没有同步到文档

交付：

- 更新 bundle 顶层 schema、页面映射、mutation endpoint、能力边界

验收：

- 文档、UI、代码三者对同一能力没有冲突叙述

### T11 发布与运行契约

问题：

- 当前 Logits 集成仍更像 workspace 开发模式
- 对外安装/验证步骤不够正式

交付：

- `pyproject` optional dependencies 整理
- Web 与 CLI 的环境检查、安装说明、能力边界统一

验收：

- 外部用户能明确知道哪些依赖来自 pip，哪些依赖来自 sibling workspace 或显式路径

## 新一轮 control-plane 与训练闭环修复

### T12 独立 Control-Plane 服务

问题：

- 首方 Dashboard API 之前仍以 `Next route -> Python subprocess -> sqlite/manifest` 为主
- 这更像本地 demo bridge，不像稳定的服务面

交付：

- 新增 `clawgraph control-plane serve`
- Dashboard bundle、feedback mutation、training actions 统一走 Python control-plane
- Next route 只做代理和兜底 fallback

验收：

- 配置 `CLAWGRAPH_CONTROL_PLANE_URL` 后，Web 读取和写入都优先走独立 control-plane 服务
- 不再要求每次请求都 shell 到本地 Python

### T13 训练工作台可操作化

问题：

- `/training` 之前只能看训练血缘，不能继续推动接替链路

交付：

- 训练页支持直接提交训练请求
- 候选出现后支持直接发起固定评测
- 评测完成后支持直接生成 handoff

验收：

- 用户在 Web 中可直接把链路从 `request -> candidate -> evaluation -> handoff` 往下推进

### T14 Mutation 身份绑定

问题：

- 写接口之前直接信任前端传来的 `reviewer`

交付：

- control-plane 写接口统一从服务端配置读取 actor
- feedback resolve / review override 不再信任调用方自报 reviewer

验收：

- 未授权调用无法写入
- 授权调用写回的 reviewer 与服务端 actor 一致，而不是前端 payload

### T15 Logits 运行契约收口

问题：

- 之前默认依赖 sibling workspace 自动探测，发行形态仍偏工程环境假设

交付：

- `CLAWGRAPH_LOGITS_SRC` / `CLAWGRAPH_LOGITS_COOKBOOK_SRC` 仍支持显式路径
- sibling workspace auto-discovery 改为 `CLAWGRAPH_ALLOW_WORKSPACE_LOGITS_DISCOVERY=1` 显式开启

验收：

- 默认环境下优先使用已安装包或显式路径
- 只有本地开发时才显式启用 workspace 探测

### T16 首方 API Smoke 与 HTTP 回归

问题：

- 之前只有 build/typecheck/e2e，没有首方 API 的权限/负载 smoke 入口

交付：

- 新增 `tests/test_control_plane.py`
- Web 增加 `test:api-auth-smoke` / `test:api-load-smoke`

验收：

- 有一条自动化回归覆盖 control-plane 的授权写入和训练链路
- 有可重复执行的 auth/load smoke 入口
