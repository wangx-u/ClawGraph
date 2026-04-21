# Agent Diff + ClawGraph Demo

这套 demo 把两条链路接在一起：

1. `agent-diff` 提供可隔离、可复现的 SaaS API replica 和 deterministic diff eval。
2. `clawgraph` 通过 `proxy` 捕获模型请求，并把任务注释、评测分数写回同一个 store。

目标不是给 `clawgraph` 增加 benchmark 专用内核逻辑，而是复用：

- `clawgraph proxy`
- `ClawGraphOpenAIClient`
- `SQLiteFactStore`
- `annotation / score` artifacts

形成一条可复跑 demo：

```text
agent-diff test
  -> model request via clawgraph proxy
  -> agent executes tool calls against agent-diff replica API
  -> agent-diff evaluates state diff
  -> clawgraph store receives model facts + annotation + score
  -> dashboard / phase2 can continue from the same store
```

## 最短命令

在 `clawgraph` 目录执行：

```bash
export DEEPSEEK_API_KEY='...'
bash ./benchmarks/agent_diff/run_agent_diff_demo.sh
```

默认行为：

- 启动 `agent-diff` 本地 docker stack
- 启动 `clawgraph proxy`
- 运行 `Slack Bench` 的第 1 条测试
- 把结果写入 `/tmp/clawgraph-agent-diff-demo.db`

## 已启动 backend 的运行方式

如果你已经自己把 `agent-diff backend` 跑起来了，不希望脚本再拉 Docker：

```bash
export DEEPSEEK_API_KEY='...'
AGENT_DIFF_BOOTSTRAP_MODE=skip \
bash ./benchmarks/agent_diff/run_agent_diff_demo.sh
```

脚本会直接复用 `AGENT_DIFF_BASE_URL` 指向的 backend；默认是 `http://127.0.0.1:8000`。

## Host Backend 参考启动方式

这条路径适合本地 demo，避免首次 `docker compose` 拉 backend 镜像太慢。

1. 安装并启动本地 Postgres：

```bash
brew install postgresql@16
brew services start postgresql@16
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
psql postgres -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    CREATE ROLE postgres LOGIN SUPERUSER PASSWORD 'postgres';
  ELSE
    ALTER ROLE postgres WITH LOGIN SUPERUSER PASSWORD 'postgres';
  END IF;
END
$$;
SQL
createdb -O postgres diff_the_universe || true
```

2. 准备 `agent-diff backend` 本地 Python 环境：

```bash
cd /Users/joker/go/src/github.com/wangx-u/agent-rl/agent-diff
uv venv /tmp/agent-diff-backend-313 --python 3.13
source /tmp/agent-diff-backend-313/bin/activate
uv pip install -r backend/pyproject.toml
```

3. 首次启动先做 migration + seed，再起 backend：

```bash
cd /Users/joker/go/src/github.com/wangx-u/agent-rl/agent-diff/backend
source /tmp/agent-diff-backend-313/bin/activate
export DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:5432/diff_the_universe'
export LOGICAL_REPLICATION_ENABLED='false'
export ENVIRONMENT='development'
alembic upgrade head
python utils/seed_slack_template.py
python utils/seed_linear_template.py
python utils/seed_box_template.py
python utils/seed_calendar_template.py
python utils/seed_github_template.py
python utils/seed_tests.py
uvicorn src.platform.api.main:app --host 127.0.0.1 --port 8000
```

4. 另一个终端跑 demo：

```bash
cd /Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph
export DEEPSEEK_API_KEY='...'
AGENT_DIFF_BOOTSTRAP_MODE=skip \
bash ./benchmarks/agent_diff/run_agent_diff_demo.sh
```

## 批量产出 Logits 训练数据

如果目标不是只验证单条链路，而是直接沉淀一批可用于 `Logits` 的 SFT 训练样本：

```bash
cd /Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph
export DEEPSEEK_API_KEY='...'
bash ./benchmarks/agent_diff/run_agent_diff_logits_pipeline.sh --json
```

默认行为：

- 复用已经启动的 `agent-diff backend`
- 在 `http://127.0.0.1:8094` 启动一套新的 `clawgraph proxy`
- 批量运行 `Slack Bench` 的稳定 pack：
  - `Send message to general channel`
  - `Create a new channel`
  - `Archive a channel`
  - `Update channel topic`
  - 到达 `4` 条成功样本后停止
- 自动执行 `phase2 run --selection-scope slice`
- 自动执行 `clawgraph logits prepare-sft`

默认输出位置：

- store: `/tmp/clawgraph-agent-diff-logits-demo.db`
- phase2 导出: `/tmp/clawgraph-agent-diff-logits-phase2`
- Logits 数据与 request manifest: `/tmp/clawgraph-agent-diff-logits-train`

本轮真实验证结果：

- 成功任务数：`4`
- 训练 cohort：`cohort_4ae4e70724814dbebaeda0ca8e2797df`
- dataset snapshot：`ds_69c0c9562fdd4cb8ba9fe28a3cc4439d`
- Logits training request：`train_45119f17ba434a12bb83d141d94b758b`
- Logits 输入数据： [ds_69c0c9562fdd4cb8ba9fe28a3cc4439d.sft.conversations.jsonl](/tmp/clawgraph-agent-diff-logits-train/ds_69c0c9562fdd4cb8ba9fe28a3cc4439d.sft.conversations.jsonl)
- training manifest： [train_45119f17ba434a12bb83d141d94b758b.sft.request.json](/tmp/clawgraph-agent-diff-logits-train/train_45119f17ba434a12bb83d141d94b758b.sft.request.json)

## 常用参数

只跑某条测试：

```bash
bash ./benchmarks/agent_diff/run_agent_diff_demo.sh \
  --suite-name "Slack Bench" \
  --test-id "11f1f410-5c85-5a9b-8be9-e4fd3c184f3d"
```

按名字选测试：

```bash
bash ./benchmarks/agent_diff/run_agent_diff_demo.sh \
  --suite-name "Slack Bench" \
  --test-name "Send direct message"
```

切换模型：

```bash
AGENT_DIFF_DEMO_MODEL=deepseek-chat \
bash ./benchmarks/agent_diff/run_agent_diff_demo.sh
```

只写模型事实，不写回 annotation / score artifacts：

```bash
bash ./benchmarks/agent_diff/run_agent_diff_demo.sh --skip-artifacts
```

## 关键输出

脚本完成后会输出：

- `AgentDiff environment`
- `AgentDiff run`
- `ClawGraph session`
- `ClawGraph run`
- `Passed`
- `Score`
- `Artifacts`

这些值可直接用于后续：

```bash
cd /Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph
PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main inspect session \
  --store sqlite:////tmp/clawgraph-agent-diff-demo.db \
  --session <clawgraph-session-id>
```

或：

```bash
PYTHONPATH=src ./.venv/bin/python -m clawgraph.cli.main replay \
  --store sqlite:////tmp/clawgraph-agent-diff-demo.db \
  --session <clawgraph-session-id>
```

## Dashboard

```bash
cd /Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/web
NEXT_PUBLIC_DATA_MODE=prod \
CLAWGRAPH_STORE_URI=sqlite:////tmp/clawgraph-agent-diff-demo.db \
CLAWGRAPH_PYTHON_BIN=/Users/joker/go/src/github.com/wangx-u/agent-rl/clawgraph/.venv/bin/python \
npm run dev -- --hostname 127.0.0.1 --port 3402
```

然后打开 [http://127.0.0.1:3402](http://127.0.0.1:3402)

## 当前边界

- 当前 demo 默认走 `Slack Bench`，因为 `BashExecutorProxy` + tool-calling 路径最稳。
- 已验证 `host backend + local Postgres + clawgraph proxy` 这条路径可以真实跑通一条 `Slack Bench` 用例，并进入 `ClawGraph E1 / export-ready`。
- `agent-diff` 的 deterministic eval 会被写回 `score` artifact。
- 任务分类会被写成通用 `annotation` artifact，方便后续 phase2 / dataset / dashboard 继续消费。
- 训练执行仍不在这条 demo 内；如果要继续走训练链路，后续从同一个 store 做导出即可。
