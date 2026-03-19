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
