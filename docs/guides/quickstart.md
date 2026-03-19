# Quickstart

## 1. Install the package

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 2. Start the proxy

```bash
clawgraph proxy --model-upstream https://your-model-endpoint \
  --tool-upstream https://your-tool-endpoint \
  --store sqlite:///clawgraph.db
```

## 3. Point your runtime to the proxy

```yaml
model_endpoint: http://localhost:8080/v1/chat/completions
tool_endpoint: http://localhost:8080/tools
```

## 4. Run the agent normally

No core runtime rewrite is required.

## 5. Inspect replay, readiness, and export

```bash
clawgraph replay --session latest
clawgraph inspect session --session latest
clawgraph readiness --session latest
clawgraph export dataset --builder sft --session latest --out out.jsonl
```
