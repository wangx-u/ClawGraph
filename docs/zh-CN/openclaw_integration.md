# 接入 OpenClaw 风格 Runtime

如果你已经有 OpenClaw 或兼容 OpenAI API 的 runtime，推荐先走 proxy 接入。

## 最小接入方式

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

把 runtime 的模型请求和工具请求改为经过 ClawGraph 代理后，你就能得到：

- 不可变的 execution facts
- session / request / branch inspect
- replay 和 readiness
- 后续可追加的 artifact 和 dataset export

而且现在这一层是零配置优先的：

- 不传 `x-clawgraph-session-id` 也能跑
- proxy 会自动生成 `session_id / run_id / request_id`
- 这些标识会回写到响应头
- 浏览器风格客户端还会拿到 session 和 run cookie，后续请求可以自动复用同一个 session 和当前 run
- 只有纯无状态请求，或者客户端没有回放 run cookie 时，proxy 才会自动开新 run
- 转发上游请求时会保留业务 cookie，只剥离内部的 ClawGraph 标识 cookie

如果你的 runtime 是 Python，也可以直接用内置 helper，不用自己拼 header：

```python
from clawgraph import ClawGraphRuntimeClient

client = ClawGraphRuntimeClient(base_url="http://127.0.0.1:8080")

response = client.chat_completions(
    {"messages": [{"role": "user", "content": "compare ART and AReaL"}]}
)

client.emit_semantic(
    kind="retry_declared",
    payload={"branch_type": "retry", "status": "succeeded"},
    branch_id="br_retry_1",
)
```

`emit_semantic()` 在不显式传目标请求 id 时，会默认绑定当前 run 里最近一次请求。  
如果你想在同一个 session 里显式开始一个新 run，可以直接调用
`client.start_new_run()`。

如果你只是走 proxy 模式的浏览器或网关客户端，也可以在下一次请求上带
`x-clawgraph-new-run: 1`，这样会在保留 session 的前提下切到一个新的 run。

如果你想直接运行仓库里的最小脚本，先看
[openclaw_proxy_minimal](../../examples/openclaw_proxy_minimal/README.md)。

需要 helper 帮你自动带上下文时，再看
[openclaw_python_helper](../../examples/openclaw_python_helper/README.md)。

如果你已经在用 OpenAI Python SDK 风格的 client，也可以看
[openclaw_openai_wrapper](../../examples/openclaw_openai_wrapper/README.md)，
用 wrapper 自动注入 `extra_headers`。

## 建议补的请求头

如果 runtime 能带上这些 header，后续 inspect 和 export 会更稳：

- `x-clawgraph-session-id`
- `x-clawgraph-run-id`
- `x-clawgraph-request-id`
- `x-clawgraph-user-id`

## 什么时候补 semantic event

只靠 proxy 时，ClawGraph 已经能推断一部分 retry / branch 信息。  
如果你希望更高保真的 branch 语义，再补 semantic event：

- `retry_declared`
- `fallback_declared`
- `controller_route_decided`
- `branch_open_declared`

## 接入后先做什么

推荐顺序：

1. `clawgraph inspect session --session latest`
2. `clawgraph list runs --session latest`
3. `clawgraph list requests --session latest`
4. `clawgraph replay --session latest`
5. `clawgraph readiness --session latest --builder sft`

如果还没有 supervision，可以先跑：

```bash
clawgraph pipeline run --session latest --builder preference --dry-run
clawgraph pipeline run --session latest --builder preference --out out/preference.jsonl
```

## 下一步

- 想看完整从首跑到导出的路径：
  看 [15 分钟路径](./fifteen_minute_path.md)
- 想排查 replay 和 branch 问题：
  看 [Replay 与调试](./replay_and_debug.md)
- 想看导出和 builder：
  看 [数据导出](./dataset_builders.md)
- 想查 CLI 细节：
  看 [CLI 参考](./cli_reference.md)
