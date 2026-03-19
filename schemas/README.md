# Schemas

This directory contains versioned protocol schemas for ClawGraph.

Rules:

- Schemas are append-only at the protocol boundary.
- Backward-incompatible changes require a new major version directory.
- Derived views are not protocol schemas.
- Facts, branches, artifacts, and semantic events each version separately.

Current version:

- `v1/event.schema.json`
- `v1/branch.schema.json`
- `v1/artifact.schema.json`
- `v1/semantic_event.schema.json`
