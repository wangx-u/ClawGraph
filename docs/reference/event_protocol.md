# Event Protocol

The event protocol defines the immutable fact layer of ClawGraph.

Design goals:

- append-only
- replayable
- versioned
- runtime-agnostic
- suitable for graph derivation

Schema file:

- [`schemas/v1/event.schema.json`](../../schemas/v1/event.schema.json)
