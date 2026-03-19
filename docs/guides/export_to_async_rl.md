# Export to Async RL

ClawGraph should remain loosely coupled from the downstream trainer.

The intended boundary is:

- ClawGraph captures and structures execution
- downstream systems consume exported datasets and lineage records

Typical export families:

- SFT samples
- preference pairs
- binary RL tuples
- teacher-target manifests
- lineage-aware export records
