# Benchmarks

ClawGraph should publish benchmarks for:

- capture throughput
- replay reconstruction correctness
- branch inference cost
- builder latency
- dataset reproducibility

Benchmarks matter because ClawGraph is a substrate, not a mockup.

Benchmark environment guides:

- [`swebench_lite/README.md`](./swebench_lite/README.md): validate ClawGraph
  against `SWE-bench Lite` and `mini-SWE-agent` using the standard two-terminal
  proxy flow, without adding benchmark-specific code paths.
