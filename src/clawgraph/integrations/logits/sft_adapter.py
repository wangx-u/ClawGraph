"""Adapters from ClawGraph SFT snapshots to Logits conversation JSONL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawgraph.protocol.models import DatasetSnapshotRecord
from clawgraph.store import SQLiteFactStore


def load_dataset_snapshot(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    dataset_snapshot_id: str,
) -> DatasetSnapshotRecord:
    """Load one dataset snapshot and validate that it exists."""

    store_instance = store or SQLiteFactStore(str(store_uri))
    snapshot = store_instance.get_dataset_snapshot(dataset_snapshot_id)
    if snapshot is None:
        raise ValueError(f"dataset snapshot not found: {dataset_snapshot_id}")
    return snapshot


def export_sft_snapshot_for_logits(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    dataset_snapshot_id: str,
    out: Path,
) -> dict[str, Any]:
    """Export one ClawGraph SFT snapshot into cookbook-friendly conversation JSONL."""

    snapshot = load_dataset_snapshot(
        store_uri=store_uri,
        store=store,
        dataset_snapshot_id=dataset_snapshot_id,
    )
    if snapshot.builder != "sft":
        raise ValueError(
            f"snapshot {dataset_snapshot_id} uses builder {snapshot.builder}, expected sft"
        )
    if not snapshot.output_path:
        raise ValueError(f"snapshot {dataset_snapshot_id} has no output path")
    source_path = Path(snapshot.output_path)
    if not source_path.exists():
        raise ValueError(f"snapshot output path does not exist: {source_path}")

    out.parent.mkdir(parents=True, exist_ok=True)
    exported_count = 0
    with source_path.open("r", encoding="utf-8") as source, out.open("w", encoding="utf-8") as handle:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            messages = row.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError(
                    f"SFT row {line_number} in {source_path} does not contain a non-empty messages list"
                )
            payload = {
                "messages": messages,
                "metadata": {
                    "dataset_snapshot_id": snapshot.dataset_snapshot_id,
                    "dataset_builder": snapshot.builder,
                    "source_request_id": row.get("request_id"),
                    "source_request_fact_id": row.get("request_fact_id"),
                    "source_response_fact_id": row.get("response_fact_id"),
                    "source_run_id": row.get("run_id"),
                    "source_session_id": row.get("session_id"),
                    "slice_id": row.get("slice_id"),
                    "task_family": row.get("task_family"),
                    "task_type": row.get("task_type"),
                    "task_instance_key": row.get("task_instance_key"),
                    "teacher_model": row.get("teacher_model"),
                },
            }
            handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
            exported_count += 1

    return {
        "dataset_snapshot_id": snapshot.dataset_snapshot_id,
        "builder": snapshot.builder,
        "source_path": str(source_path),
        "output_path": str(out),
        "record_count": exported_count,
    }

