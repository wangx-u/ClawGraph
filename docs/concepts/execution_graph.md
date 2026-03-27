# Execution Graph

The execution graph is a derived structure built from immutable facts.

It organizes runtime behavior into views such as:

- session view
- run view
- branch tree
- replay timeline
- causality-aware graph

Facts are immutable. Graphs are derived.

Terminology note:

- a session may contain multiple runs
- a run is the current episode abstraction in ClawGraph v1
- requests and branches are interpreted inside one run
