# Execution Facts

Execution facts are the immutable source records of ClawGraph.

Examples:

- request started
- response finished
- tool call started
- tool call finished
- error raised
- final response sent

Facts are append-only and versioned. They are never overwritten in place.
