# Contributing

Thanks for contributing to ClawGraph.

## Project priorities

Contributions should reinforce the core boundary:

- capture execution facts
- derive graph and replay views
- attach supervision externally
- export reusable datasets

ClawGraph should not grow into a runtime or trainer.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m compileall src
```

## Contribution rules

- Keep protocol changes explicit and versioned.
- Do not mutate historical facts in-place.
- Add tests for every new schema or builder behavior.
- Prefer small PRs with one clear concern.
- When adding new behavior, update docs and examples in the same change.

## RFCs

Open an RFC for:

- new event categories
- new artifact families
- new builder families
- semantic contract changes

## Code style

- Python 3.11+
- type hints for public interfaces
- standard library first for early scaffolding
- comments only where the design is non-obvious
