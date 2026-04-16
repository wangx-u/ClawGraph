# ClawGraph Web

ClawGraph 面向用户的 Dashboard 前端，基于 Next.js App Router、TypeScript 和 Tailwind CSS 实现。

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
```

说明：

- `CLAWGRAPH_STORE_URI` 支持相对路径，路径相对于 `clawgraph/web` 目录解析。
- 本地 store bridge 由 `scripts/prod_dashboard_bundle.py` 调用共享 Python read model 聚合真实数据。
- 本地写操作 bridge 由 `scripts/prod_dashboard_action.py` 提供，目前支持人工复核相关的
  `review / resolve / override`。
- 当前已验证本地 store 模式下，Dashboard 读取、详情页 manifest 展示，以及人工复核闭环
  都可直接运行。

## 推荐联调方式

如果你要和 ClawGraph proxy / mini-SWE-agent 联调，推荐直接把 Web 连到同一个 store：

```bash
NEXT_PUBLIC_DATA_MODE=prod \
CLAWGRAPH_STORE_URI=sqlite:////tmp/clawgraph-benchmark-collection.db \
CLAWGRAPH_PYTHON_BIN=/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/.venv/bin/python \
npm run dev -- --hostname 127.0.0.1 --port 3402
```

然后访问：

- `/`：总览
- `/access`：接入质量与最新运行
- `/datasets/:snapshotId`：真实 manifest 明细
- `/evaluation/:suiteId`：验证资产与 scorecard 明细
- `/feedback`：人工复核

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
- `mock` 模式只用于纯前端设计联调；`prod` 模式下没有真实数据时页面保持空态，
  不再伪造运行结果

## 本地写操作说明

只有在 `local-store` 模式下，Web 页面才会打开人工复核写操作：

- `人工确认并入池`
- `标记已人工确认`
- `关闭当前事项`

如果当前数据源是远端 HTTP bundle，页面会明确显示为只读，因为远端 mutation API 还没有
单独暴露。

## 校验

```bash
npm run typecheck
npm run lint
npm run build
npm run test:e2e
```

`test:e2e` 会：

- 用 `scripts/seed_e2e_store.py` 生成一份确定性的本地 store
- 启动一个 prod/local-store 模式的 Next 服务
- 覆盖首页、接入页、数据集详情、cohort 详情、evaluation 详情和人工复核操作
- 校验页面展示的是人类可读标题、真实 manifest 字段和可执行的人工复核动作

如需单独启动这套 e2e 环境：

```bash
bash scripts/run_e2e_server.sh
```

## 文档

- `docs/development-spec.md`
- `docs/todo.md`
- `docs/api-contract.zh-CN.md`
