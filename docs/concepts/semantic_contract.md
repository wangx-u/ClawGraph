# Semantic Contract

Some learning-relevant semantics are hard to infer from transport traffic
alone.

The semantic contract allows runtimes to emit higher-level signals such as:

- plan created
- subgoal selected
- retry declared
- fallback declared
- branch open reason
- controller route decided
- stop reason

Proxy-first is the default path. Semantics come later when fidelity matters.
