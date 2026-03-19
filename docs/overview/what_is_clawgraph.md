# What is ClawGraph?

ClawGraph is a learning-native execution substrate for OpenClaw-style agents.

It captures immutable execution facts from real runtime execution, derives
branch-aware graph views, attaches typed supervision artifacts, and exports
reusable datasets for downstream training systems.

ClawGraph sits between:

- runtime execution
- evaluation and supervision
- dataset construction
- async RL and distillation

It does not replace the runtime, and it does not prescribe one training
algorithm.
