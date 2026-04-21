# ClawGraph Web

ClawGraph 面向用户的 Dashboard 前端，基于 Next.js App Router、TypeScript 和 Tailwind CSS 实现。
当前更适合的产品口径是：把真实 agent 运行沉淀为训练数据、验证资产和替代建议的控制面。
这套 Web 已经可以支撑工程预览、定向合作和 self-hosted demo；在安全、权限、性能和服务化继续补齐之前，不建议把它宣称为完整托管平台。

## 对外口径

一句话建议这样讲：

- ClawGraph 是一层把真实 agent 运行自动沉淀为训练数据、验证资产和替代建议的控制面。

三句展开建议固定为：

- 接入任何通过 proxy 调模型的 agent 运行流量。
- 把运行自动整理成训练数据、验证资产和人工复核队列。
- 在统一控制面里比较候选模型，并给出替代与放量建议。

边界也建议同时写清：

- ClawGraph 不是 agent runtime。
- ClawGraph 不是训练引擎。
- ClawGraph 不直接替代外部 serving/router。
- 训练执行可以接 `Logits`，ClawGraph 负责数据、评测和替代建议。

## 本地运行

```bash
npm install
npm run dev
```

默认展示中文和浅色科技风界面。

## 数据模式

通过环境变量切换：

- `NEXT_PUBLIC_DATA_MODE=mock`
  使用内置演示数据，适合纯前端联调和设计验收。
- `NEXT_PUBLIC_DATA_MODE=prod`
  优先请求真实 HTTP API：`GET /dashboard/bundle`
- 当 `prod` 模式下 HTTP API 未配置或不可用时，自动回退到本地 ClawGraph Store。
- 当 `prod` 模式下既没有 HTTP API，也没有本地 store 时，页面保持空状态，不再注入
  mock 数据伪装成真实结果。

推荐环境变量：

```bash
NEXT_PUBLIC_DATA_MODE=prod
NEXT_PUBLIC_CLAWGRAPH_API_BASE_URL=http://127.0.0.1:8013
CLAWGRAPH_STORE_URI=../../tmp-bootstrap.db
CLAWGRAPH_PYTHON_BIN=python3
CLAWGRAPH_TRAINING_MANIFEST_DIR=../../tmp-logits-manifests
```

说明：

- `CLAWGRAPH_STORE_URI` 支持相对路径，路径相对于 `clawgraph/web` 目录解析。
- 首方 HTTP API 由 Next route handler 暴露：
  - `GET /dashboard/bundle`
  - `POST /dashboard/feedback/resolve`
  - `POST /dashboard/feedback/review-override`
- 当 Web 部署本身可访问 store 时，远端模式和本地模式会共享同一套 bundle / mutation 能力。
- 本地 store bridge 由 `scripts/prod_dashboard_bundle.py` 调用共享 Python read model 聚合真实数据。
- `CLAWGRAPH_TRAINING_MANIFEST_DIR` 用于把训练请求、候选模型、评测执行和路由交接
  manifest 一并纳入 Dashboard bundle。
- 本地写操作 bridge 由 `scripts/prod_dashboard_action.py` 提供，目前支持人工复核相关的
  `review / resolve / override`。
- 当前已验证首方 HTTP API 模式下，Dashboard 读取、详情页训练血缘展示，以及人工复核闭环
  都可直接运行。
- 训练资产页面当前主要负责查看训练血缘和结果；训练提交、评测执行和 handoff 仍可通过
  CLI / 外部训练系统驱动。

## 推荐联调方式

如果你要和 ClawGraph proxy / mini-SWE-agent 联调，推荐直接把 Web 连到同一个 store：

```bash
NEXT_PUBLIC_DATA_MODE=prod \
CLAWGRAPH_STORE_URI=sqlite:////tmp/clawgraph-benchmark-collection.db \
CLAWGRAPH_PYTHON_BIN=/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/.venv/bin/python \
CLAWGRAPH_TRAINING_MANIFEST_DIR=/tmp/clawgraph-benchmark-collection-manifests \
npm run dev -- --hostname 127.0.0.1 --port 3402
```

然后访问：

- `/`：总览
- `/access`：接入质量与最新运行
- `/datasets/:snapshotId`：真实 manifest 明细
- `/training`：训练请求、候选模型、评测执行和交接状态
- `/training/requests/:requestId`：训练请求详情与下游血缘
- `/training/candidates/:candidateId`：候选模型详情与产物路径
- `/training/evaluations/:executionId`：评测执行、scorecard 与 promotion 关联
- `/training/handoffs/:handoffId`：router handoff、rollback 条件与 route config
- `/evaluation/:suiteId`：验证资产与 scorecard 明细
- `/feedback`：人工复核
- `/coverage`：基于真实 decision / rollback 条件的覆盖建议

当前产品口径已经对齐为：

- `请求归属清晰度`
- `任务标签覆盖率`
- `决策语义覆盖率`
- `已生成验证资产`

不再使用会误导用户的旧文案，例如“任务识别清晰度”或“可评估运行”。

页面展示逻辑也已经统一：

- run / session 优先显示任务标题、仓库和实例摘要，原始对象 id 只保留为短标签
- replay / access 会把请求归类成 `模型推理 / 工具调用 / 运行时事件` 等步骤类型
- 原始接口路径例如 `/chat/completions` 会降级为技术细节，不再充当步骤主标题
- Coverage 页面只展示真实候选模型、真实 decision / recommended stage 和真实 rollback 条件；
  不再把静态示例规则伪装成当前策略
- Training 页面会读取训练资产 manifest，把 `training request -> candidate -> eval execution -> handoff`
  和 store-backed training registry 一起放在同一条血缘链上查看
- Training 页面现在也支持直接继续动作：提交训练、发起评测、生成交接
- Training 详情页会继续把这条血缘展开到单个对象，而不是只停留在列表页
- `mock` 模式只用于纯前端设计联调；`prod` 模式下没有真实数据时页面保持空态，
  不再伪造运行结果

## Logits 运行契约

如果你要使用 `clawgraph logits ...` 命令或让 Web 读取真实训练资产，先检查运行时：

```bash
cd ..
PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main logits doctor --json
```

当 `logits` 或 `logits-cookbook` 不是通过当前 Python 环境直接安装时，可以显式设置：

```bash
export CLAWGRAPH_LOGITS_SRC=/abs/path/to/logits/src
export CLAWGRAPH_LOGITS_COOKBOOK_SRC=/abs/path/to/logits-cookbook
```

如果只是本地开发临时复用同级 workspace，再显式开启：

```bash
export CLAWGRAPH_ALLOW_WORKSPACE_LOGITS_DISCOVERY=1
```

如果你想先看当前 manifest 目录是否已经形成完整训练血缘，可以运行：

```bash
cd ..
PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main logits registry \
  --manifest-dir /tmp/clawgraph-manifests \
  --store sqlite:///clawgraph.db \
  --json
```

## 写操作说明

推荐的服务化接法是先起独立 control-plane：

```bash
cd ..
PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main control-plane serve \
  --store sqlite:///clawgraph.db \
  --manifest-dir /tmp/clawgraph-manifests \
  --host 127.0.0.1 \
  --port 8787 \
  --auth-token dev-token \
  --actor clawgraph.control_plane
```

然后让 Web 指向它：

```bash
export NEXT_PUBLIC_DATA_MODE=prod
export NEXT_PUBLIC_CLAWGRAPH_API_BASE_URL=http://127.0.0.1:8787
export CLAWGRAPH_CONTROL_PLANE_URL=http://127.0.0.1:8787
export CLAWGRAPH_CONTROL_PLANE_TOKEN=dev-token
```

当当前部署满足下面任一条件时，Web 页面会打开人工复核和训练动作：

- `NEXT_PUBLIC_CLAWGRAPH_API_BASE_URL` 指向首方 Dashboard HTTP API
- 当前 Web 自己持有 `CLAWGRAPH_STORE_URI`

- `人工确认并入池`
- `标记已人工确认`
- `关闭当前事项`

只有在既没有首方 HTTP API，又没有本地 store 写入能力时，页面才会显示为只读。

## 发布验证分层

当前已经覆盖：

- `npm run typecheck`
- `npm run lint`
- `npm run build`
- `npm run test:e2e`
- `npm run test:api-auth-smoke`
- `npm run test:api-load-smoke`

这意味着当前已经证明：

- 页面口径和后端 bundle 能对齐
- 首页、接入页、详情页、训练资产页和人工复核关键路径可工作
- 首方 HTTP API 路径已经能驱动真实 bundle 和基础写操作
- 已有可重复执行的未授权写入与 bundle 读取负载 smoke 入口

但当前仍未把以下内容视为“已经完成验证”：

- 多用户身份、审计和更完整的服务化治理
- 系统级压测、混沌与滥用测试
- 多租户、远端托管和大规模并发部署行为

因此，对外更准确的状态仍然是：

- `高级技术预览`
- `定向合作预览`
- `self-hosted 工程控制面`

## 校验

```bash
npm run typecheck
npm run lint
npm run build
npm run test:e2e
```

`test:e2e` 会：

- 用 `scripts/seed_e2e_store.py` 生成一份确定性的本地 store
- 生成对应的训练资产 manifest
- 启动一个 prod/local-store 模式的 Next 生产服务
- 覆盖首页、接入页、数据集详情、cohort 详情、evaluation 详情和人工复核操作
- 覆盖训练资产页和覆盖策略页
- 校验页面展示的是人类可读标题、真实 manifest 字段和可执行的人工复核动作

如需单独启动这套 e2e 环境：

```bash
bash scripts/run_e2e_server.sh
```

## 文档

- `docs/development-spec.md`
- `docs/todo.md`
- `docs/api-contract.zh-CN.md`
- `../docs/guides/public_positioning.zh-CN.md`
