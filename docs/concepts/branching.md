# Branching

Branching is a first-class concept in ClawGraph because agent learning depends
on retries, fallbacks, repairs, subagents, and sibling comparisons.

Core branch types in v1:

- `mainline`
- `retry`
- `fallback`
- `repair`
- `subagent`
- `explore`

Branches can be inferred from proxy traffic or declared by the runtime through
the semantic contract.

The early inspect surfaces always distinguish:

- `source=inferred`
- `source=declared`

Branch inference v1 currently focuses on:

- mainline detection
- retry detection after failed attempts
- hinted subagent branches through context headers

Declared branch support currently focuses on:

- `retry_declared`
- `fallback_declared`
- `branch_open_declared`
- `branch_close_declared`
