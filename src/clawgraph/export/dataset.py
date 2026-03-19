"""Dataset export helpers for the early ClawGraph MVP."""

from __future__ import annotations

import json
from pathlib import Path

from clawgraph.protocol.models import FactEvent
from clawgraph.store import SQLiteFactStore


def _fact_to_json(fact: FactEvent) -> dict:
    return {
        "fact_id": fact.fact_id,
        "schema_version": fact.schema_version,
        "run_id": fact.run_id,
        "session_id": fact.session_id,
        "thread_id": fact.thread_id,
        "task_id": fact.task_id,
        "parent_ref": fact.parent_ref,
        "branch_id": fact.branch_id,
        "timestamp": fact.timestamp.isoformat(),
        "actor": fact.actor,
        "kind": fact.kind,
        "payload": fact.payload,
        "metadata": fact.metadata,
    }


def _build_facts(facts: list[FactEvent]) -> list[dict]:
    return [_fact_to_json(fact) for fact in facts]


def _build_sft(facts: list[FactEvent]) -> list[dict]:
    requests_by_id = {
        fact.fact_id: fact
        for fact in facts
        if fact.kind == "request_started" and fact.actor == "model"
    }

    samples: list[dict] = []
    for fact in facts:
        if fact.kind != "response_finished" or fact.actor != "model":
            continue

        parent_ref = fact.parent_ref
        if parent_ref is None or parent_ref not in requests_by_id:
            continue

        request = requests_by_id[parent_ref]
        request_json = request.payload.get("json")
        response_json = fact.payload.get("json")
        if not isinstance(request_json, dict) or not isinstance(response_json, dict):
            continue

        messages = request_json.get("messages")
        choices = response_json.get("choices")
        if not isinstance(messages, list) or not isinstance(choices, list) or not choices:
            continue

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            continue
        message = first_choice.get("message")
        if not isinstance(message, dict):
            continue

        sample_messages = list(messages)
        sample_messages.append(message)
        samples.append(
            {
                "session_id": fact.session_id,
                "request_fact_id": request.fact_id,
                "response_fact_id": fact.fact_id,
                "messages": sample_messages,
            }
        )

    return samples


def export_dataset(*, store_uri: str, builder: str, session: str, out: Path) -> int:
    """Export a dataset from the stored facts for a session."""

    store = SQLiteFactStore(store_uri)
    session_id = store.get_latest_session_id() if session == "latest" else session
    if session_id is None:
        raise ValueError("no sessions found in store")

    facts = store.list_facts(session_id)
    if builder == "facts":
        records = _build_facts(facts)
    elif builder == "sft":
        records = _build_sft(facts)
    else:
        raise ValueError(f"unsupported builder: {builder}")

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True))
            handle.write("\n")

    return len(records)
