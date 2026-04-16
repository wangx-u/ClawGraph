"""Adapters from ClawGraph preference snapshots to Logits comparison JSONL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawgraph.integrations.logits.sft_adapter import load_dataset_snapshot
from clawgraph.store import SQLiteFactStore


def _normalize_message_sequence(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        role = item.get("role")
        content = item.get("content")
        if not isinstance(role, str):
            return None
        normalized.append(
            {
                "role": role,
                "content": content,
            }
        )
    return normalized


def _assistant_message(content: str) -> dict[str, str]:
    return {"role": "assistant", "content": content}


def _completion_messages_from_branch(branch_payload: Any) -> list[dict[str, Any]] | None:
    if not isinstance(branch_payload, dict):
        return None
    trajectory = branch_payload.get("trajectory")
    if isinstance(trajectory, list):
        messages: list[dict[str, Any]] = []
        for step in trajectory:
            if not isinstance(step, dict):
                continue
            output_message = step.get("output_message")
            normalized_output = _normalize_message_sequence([output_message]) if isinstance(output_message, dict) else None
            if normalized_output:
                messages.extend(normalized_output)
                continue
            response = step.get("response")
            if isinstance(response, dict):
                assistant_message = response.get("assistant_message")
                normalized_response = (
                    _normalize_message_sequence([assistant_message])
                    if isinstance(assistant_message, dict)
                    else None
                )
                if normalized_response:
                    messages.extend(normalized_response)
        if messages:
            return messages
    terminal_output = branch_payload.get("terminal_output")
    if isinstance(terminal_output, dict):
        message = terminal_output.get("message")
        normalized_message = (
            _normalize_message_sequence([message]) if isinstance(message, dict) else None
        )
        if normalized_message:
            return normalized_message
        error = terminal_output.get("error")
        if isinstance(error, dict) and error:
            return [_assistant_message(json.dumps(error, ensure_ascii=True, sort_keys=True))]
    if isinstance(terminal_output, str) and terminal_output.strip():
        return [_assistant_message(terminal_output)]
    return None


def export_preference_snapshot_for_logits(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    dataset_snapshot_id: str,
    train_out: Path,
    test_out: Path | None = None,
    test_size: int = 0,
) -> dict[str, Any]:
    """Export one ClawGraph preference snapshot into labeled comparison JSONL."""

    snapshot = load_dataset_snapshot(
        store_uri=store_uri,
        store=store,
        dataset_snapshot_id=dataset_snapshot_id,
    )
    if snapshot.builder != "preference":
        raise ValueError(
            f"snapshot {dataset_snapshot_id} uses builder {snapshot.builder}, expected preference"
        )
    if not snapshot.output_path:
        raise ValueError(f"snapshot {dataset_snapshot_id} has no output path")
    source_path = Path(snapshot.output_path)
    if not source_path.exists():
        raise ValueError(f"snapshot output path does not exist: {source_path}")
    if test_size > 0 and test_out is None:
        raise ValueError("test_out is required when test_size is greater than 0")

    rows: list[dict[str, Any]] = []
    with source_path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            prompt_conversation = _normalize_message_sequence(row.get("prompt"))
            chosen_messages = _completion_messages_from_branch(row.get("chosen"))
            rejected_messages = _completion_messages_from_branch(row.get("rejected"))
            if not prompt_conversation or not chosen_messages or not rejected_messages:
                raise ValueError(
                    "preference row "
                    f"{line_number} in {source_path} is missing prompt or completion messages"
                )
            rows.append(
                {
                    "comparison": {
                        "prompt_conversation": prompt_conversation,
                        "completion_A": chosen_messages,
                        "completion_B": rejected_messages,
                    },
                    "label": "A",
                    "metadata": {
                        "dataset_snapshot_id": snapshot.dataset_snapshot_id,
                        "dataset_builder": snapshot.builder,
                        "source_run_id": row.get("run_id"),
                        "source_session_id": row.get("session_id"),
                        "source": row.get("source"),
                        "slice_id": row.get("slice_id"),
                        "task_family": row.get("task_family"),
                        "task_type": row.get("task_type"),
                        "task_instance_key": row.get("task_instance_key"),
                    },
                }
            )

    test_rows = rows[:test_size] if test_size > 0 else []
    train_rows = rows[test_size:] if test_size > 0 else rows

    train_out.parent.mkdir(parents=True, exist_ok=True)
    with train_out.open("w", encoding="utf-8") as handle:
        for row in train_rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
    if test_out is not None:
        test_out.parent.mkdir(parents=True, exist_ok=True)
        with test_out.open("w", encoding="utf-8") as handle:
            for row in test_rows:
                handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True))
                handle.write("\n")

    return {
        "dataset_snapshot_id": snapshot.dataset_snapshot_id,
        "builder": snapshot.builder,
        "source_path": str(source_path),
        "train_output_path": str(train_out),
        "test_output_path": None if test_out is None else str(test_out),
        "train_record_count": len(train_rows),
        "test_record_count": len(test_rows),
    }
