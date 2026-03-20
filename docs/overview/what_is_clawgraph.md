# What is ClawGraph?

ClawGraph is a learning-native execution substrate for OpenClaw-style agents.

It captures immutable execution facts from real runtime execution, derives
branch-aware graph views, attaches typed supervision artifacts, and exports
reusable datasets for downstream training systems.

In practice, one captured run can support:

- replay and debugging
- post hoc scoring and ranking
- readiness checks
- SFT export
- preference export
- binary RL export

ClawGraph sits between:

- runtime execution
- evaluation and supervision
- dataset construction
- async RL and distillation

It does not replace the runtime, and it does not prescribe one training
algorithm.

Use ClawGraph when:

- your agent runtime already exists
- logs are not structured enough for training reuse
- retries and fallbacks matter for sample quality
- you want to add richer semantics gradually instead of all at once
