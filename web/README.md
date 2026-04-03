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

推荐环境变量：

```bash
NEXT_PUBLIC_DATA_MODE=prod
NEXT_PUBLIC_CLAWGRAPH_API_BASE_URL=http://127.0.0.1:8013
CLAWGRAPH_STORE_URI=../../tmp-bootstrap.db
CLAWGRAPH_PYTHON_BIN=python3
```

说明：

- `CLAWGRAPH_STORE_URI` 支持相对路径，路径相对于 `clawgraph/web` 目录解析。
- 本地 store bridge 由 `scripts/prod_dashboard_bundle.py` 负责聚合真实数据。
- 当前已验证 `../../tmp-bootstrap.db` 可以成功生成 dashboard bundle。

## 校验

```bash
npm run typecheck
npm run lint
npm run build
```

## 文档

- `docs/development-spec.md`
- `docs/todo.md`
- `docs/api-contract.zh-CN.md`
