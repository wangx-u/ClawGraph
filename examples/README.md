# Examples

Pick the example that matches what you want to do next.

## Recommended order

1. [`openclaw_quickstart`](openclaw_quickstart/README.md)
2. [`openclaw_proxy_minimal`](openclaw_proxy_minimal/README.md)
3. [`openclaw_with_headers`](openclaw_with_headers/README.md)
4. [`openclaw_with_semantic_contract`](openclaw_with_semantic_contract/README.md)
5. [`export_to_async_rl`](export_to_async_rl/README.md)

## Example catalog

| Example | Best for | What you get |
| --- | --- | --- |
| [`openclaw_quickstart`](openclaw_quickstart/README.md) | A full first run | Capture, one declared branch, artifacts, readiness, and export |
| [`openclaw_proxy_minimal`](openclaw_proxy_minimal/README.md) | Lowest-friction integration | Route model and tool traffic through ClawGraph and inspect captured runs |
| [`openclaw_with_headers`](openclaw_with_headers/README.md) | Stable identity and correlation | Cleaner session, run, request, and user-level inspection |
| [`openclaw_with_semantic_contract`](openclaw_with_semantic_contract/README.md) | Higher-fidelity branching | Declared retry, fallback, and routing signals for better exports |
| [`export_to_async_rl`](export_to_async_rl/README.md) | Training handoff | SFT, preference, and binary RL exports with manifests |

## Which example should I start with?

- If you are new to the repository, start with
  [`openclaw_quickstart`](openclaw_quickstart/README.md).
- If you already run an OpenClaw-style stack, start with
  [`openclaw_proxy_minimal`](openclaw_proxy_minimal/README.md).
- If your replay quality depends on stable ids, use
  [`openclaw_with_headers`](openclaw_with_headers/README.md).
- If retry and fallback correctness matters for training, use
  [`openclaw_with_semantic_contract`](openclaw_with_semantic_contract/README.md).
- If you already have captured sessions and need training files, use
  [`export_to_async_rl`](export_to_async_rl/README.md).
