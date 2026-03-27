# OpenClaw Quickstart

This example shows the smallest useful ClawGraph loop for an OpenClaw-style
runtime:

1. capture real traffic
2. declare one semantic branch
3. attach one reward artifact and one preference artifact
4. inspect readiness
5. export SFT, preference, and binary RL datasets

## 1. Start the proxy

```bash
clawgraph proxy \
  --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

## 2. Point the runtime at the proxy

```yaml
model_endpoint: http://localhost:8080/v1/chat/completions
tool_endpoint: http://localhost:8080/tools
headers:
  x-clawgraph-session-id: sess_openclaw_1
  x-clawgraph-run-id: run_openclaw_1
  x-clawgraph-user-id: user_seed
```

If you do not need stable ids yet, you can also let the proxy assign them. This
example keeps them explicit only to make the walkthrough deterministic.

## 3. Append one semantic event

```bash
curl -X POST http://localhost:8080/v1/semantic-events \
  -H "Content-Type: application/json" \
  -d @examples/openclaw_quickstart/retry_declared.json
```

## 4. Attach supervision

```bash
clawgraph artifact append \
  --session-id sess_openclaw_1 \
  --run-id run_openclaw_1 \
  --type score \
  --target-ref latest-response \
  --producer judge-v1 \
  --payload @examples/openclaw_quickstart/score_payload.json

clawgraph artifact append \
  --session-id sess_openclaw_1 \
  --run-id run_openclaw_1 \
  --type preference \
  --target-ref run:latest \
  --producer judge-v1 \
  --payload @examples/openclaw_quickstart/preference_payload.json
```

## 5. Inspect before export

```bash
clawgraph inspect session --session sess_openclaw_1
clawgraph list runs --session sess_openclaw_1
clawgraph list requests --session sess_openclaw_1
clawgraph inspect request --session sess_openclaw_1 --request-id latest
clawgraph inspect branch --session sess_openclaw_1
clawgraph readiness --session sess_openclaw_1 --builder preference
clawgraph export dataset --builder preference --session sess_openclaw_1 --dry-run
```

## 6. Derive supervision without hand-authored JSON

For a real captured session, use built-in supervision templates:

```bash
clawgraph artifact bootstrap --template openclaw-defaults --session sess_openclaw_1 --dry-run
clawgraph artifact bootstrap --template openclaw-defaults --session sess_openclaw_1
```

## 7. Export builders

```bash
clawgraph export dataset --builder sft --session sess_openclaw_1 --out exports/sft.jsonl
clawgraph export dataset --builder preference --session sess_openclaw_1 --out exports/preference.jsonl
clawgraph export dataset --builder binary_rl --session sess_openclaw_1 --out exports/binary_rl.jsonl
```

Each export writes:

- `*.jsonl`
- `*.jsonl.manifest.json`
