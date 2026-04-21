# ClawGraph Dashboard API Contract

## 目标

定义前端 Dashboard 所依赖的聚合接口 contract，并明确 `mock / prod / prod-fallback` 的切换规则。

当前前端默认读取中文文案，并约定所有状态、标签和聚合字段已经完成服务端归一化，前端不再自行拼业务语义。

## 数据模式与优先级

当 `NEXT_PUBLIC_DATA_MODE=mock` 时：

- 直接使用 `src/lib/mock-data.ts`

当 `NEXT_PUBLIC_DATA_MODE=prod` 时：

1. 优先请求真实 HTTP API：`GET /dashboard/bundle`
2. 若 HTTP API 不可用，且配置了 `CLAWGRAPH_STORE_URI`，则调用本地 bridge：
   - `scripts/prod_dashboard_bundle.py`
3. 若以上都不可用，则返回空的 prod bundle，并把数据源状态标记为 `prod-fallback`

## 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `NEXT_PUBLIC_DATA_MODE` | 是 | `mock` 或 `prod` |
| `NEXT_PUBLIC_CLAWGRAPH_API_BASE_URL` | 否 | 真实 API Base URL，例如 `http://127.0.0.1:8013` |
| `CLAWGRAPH_STORE_URI` | 否 | 本地 ClawGraph Store 路径，支持相对路径 |
| `CLAWGRAPH_PYTHON_BIN` | 否 | 执行本地 bridge 的 Python，可缺省为 `python3` |

## HTTP Contract

### Endpoint

- Method: `GET`
- Path: `/dashboard/bundle`

### Mutation Endpoints

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/dashboard/feedback/resolve` | 更新一个反馈事项状态为 `reviewed` 或 `resolved` |
| `POST` | `/dashboard/feedback/review-override` | 对一个 run 追加人工确认结果，并可同步关闭对应反馈项 |

### 响应格式

支持两种响应形态，前端都会兼容：

1. 直接返回 `DashboardBundle`
2. 返回 envelope：

```json
{
  "bundle": {},
  "meta": {
    "statusText": "当前使用真实 HTTP 数据源"
  }
}
```

## `DashboardBundle` 顶层结构

```ts
type DashboardBundle = {
  overviewMetrics: Metric[];
  healthMatrix: HealthItem[];
  opportunities: OpportunityItem[];
  risks: RiskItem[];
  ingestSummary: IngestSummary;
  workflowLanes: WorkflowLane[];
  workflowRuns: WorkflowRun[];
  sessions: SessionSummary[];
  replayRecords: ReplayRecord[];
  artifacts: Artifact[];
  slices: SliceRecord[];
  candidates: Candidate[];
  cohorts: CohortSummary[];
  readinessRows: BuilderReadiness[];
  snapshots: DatasetSnapshot[];
  evalSuites: EvalSuite[];
  scorecards: Scorecard[];
  coverageRows: CoverageRow[];
  coverageGuardrails: string[];
  feedbackItems: FeedbackItem[];
  trainingRegistrySummary: TrainingRegistrySummary;
  trainingRequests: TrainingRequest[];
  modelCandidates: ModelCandidate[];
  evalExecutions: EvalExecution[];
  routerHandoffs: RouterHandoff[];
  jobs: JobItem[];
}
```

字段类型定义以 [src/lib/types.ts](/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/web/src/lib/types.ts) 为准。

## 页面与字段映射

| 页面 | 主要字段 |
| --- | --- |
| `/` | `overviewMetrics`, `healthMatrix`, `opportunities`, `risks`, `jobs` |
| `/sessions` | `sessions` |
| `/sessions/[sessionId]/runs/[runId]/replay` | `replayRecords`, `artifacts`, `sessions` |
| `/supervision` | `artifacts` |
| `/curation/slices` | `slices` |
| `/curation/candidates` | `candidates` |
| `/curation/cohorts/[cohortId]` | `cohorts` |
| `/datasets` | `readinessRows`, `snapshots` |
| `/evaluation` | `evalSuites`, `scorecards` |
| `/coverage` | `coverageRows` |
| `/feedback` | `feedbackItems` |
| `/training` | `trainingRegistrySummary`, `trainingRequests`, `modelCandidates`, `evalExecutions`, `routerHandoffs` |
| `/training/requests/[requestId]` | `trainingRequests`, `modelCandidates`, `evalExecutions`, `routerHandoffs` |
| `/training/candidates/[candidateId]` | `modelCandidates`, `trainingRequests`, `evalExecutions`, `routerHandoffs` |
| `/training/evaluations/[executionId]` | `evalExecutions`, `modelCandidates` |
| `/training/handoffs/[handoffId]` | `routerHandoffs`, `modelCandidates` |

## 数据源状态 contract

前端 Shell 会展示一个统一的数据源状态对象：

```ts
type DataSourceMeta = {
  configuredMode: "mock" | "prod";
  resolvedMode: "mock" | "prod";
  locale: "zh-CN";
  apiBaseUrl?: string;
  storeUri?: string;
  provider: "mock" | "remote-http" | "local-store" | "prod-fallback";
  status: "mock" | "prod" | "prod-fallback";
  statusText: string;
  supportsMutations?: boolean;
}
```

含义：

- `configuredMode` 表示 env 中声明的目标模式
- `resolvedMode` 表示当前实际使用的数据模式
- `provider` 表示真实来源
- `statusText` 直接用于顶部状态栏
- `supportsMutations` 表示当前数据源是否允许在 Web 内直接执行复核写操作

## 本地 Store Bridge

本地 bridge 不依赖 HTTP API，直接从 sqlite store 聚合真实 dashboard bundle：

```bash
python3 scripts/prod_dashboard_bundle.py --store ../../tmp-bootstrap.db
```

已验证结果：

- `../../tmp-bootstrap.db` 在 `clawgraph/web` 下可直接使用
- 脚本会自动把相对路径转换为绝对 sqlite store 路径

## 兼容性约束

- 所有时间字段应优先输出为已格式化字符串，避免前端再做时区推断
- 所有状态字段应使用前端 presenter 已支持的枚举值
- `DashboardBundle` 中允许空数组，不应返回 `null`
- 若某一子域暂时没有数据，仍应返回完整顶层结构，保持页面稳定
