# FAQ

## Does ClawGraph replace OpenClaw?

No. OpenClaw remains the runtime. ClawGraph captures and structures execution
for replay and learning reuse.

## Does ClawGraph require runtime rewrites?

Not in the default path. Start with proxy-first capture.

## Is ClawGraph a trainer?

No. It exports datasets and lineage into downstream async RL and distillation
systems.

## Why keep artifacts external?

Because learning logic changes quickly. Immutable facts must remain reusable.
