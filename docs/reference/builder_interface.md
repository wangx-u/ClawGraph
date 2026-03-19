# Builder Interface

A dataset builder consumes graph and artifact views and emits a dataset.

Conceptual interface:

```python
build(
    trajectory_view,
    artifact_view,
    memory_view=None,
    context=None,
)
```

Builder scaffolding in code:

- [`src/clawgraph/builders/interfaces.py`](../../src/clawgraph/builders/interfaces.py)
