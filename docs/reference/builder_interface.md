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

Reference implementation:

- `src/clawgraph/builders/interfaces.py`
