"""Dataset export helpers for ClawGraph."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clawgraph.graph import build_branch_inspect_summaries, build_comparable_branch_pairs
from clawgraph.protocol.models import ArtifactRecord, FactEvent
from clawgraph.store import SQLiteFactStore

SUPPORTED_BUILDERS = ("facts", "sft", "preference", "binary_rl")
_PREFERENCE_ARTIFACT_TYPES = {
    "preference",
    "preference_pair",
    "chosen_rejected",
    "ranking",
}
_BINARY_RL_ARTIFACT_TYPES = {
    "score",
    "reward",
    "binary_label",
    "label",
}


@dataclass(slots=True)
class ExportPlan:
    """Planned dataset export including preview information."""

    builder: str
    session_id: str
    run_id: str | None
    output_path: str | None
    record_count: int
    blockers: list[str]
    manifest: dict[str, Any]
    records: list[dict[str, Any]]

    @property
    def ready(self) -> bool:
        return not self.blockers and self.record_count > 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ready"] = self.ready
        return payload


def _fact_to_json(fact: FactEvent) -> dict[str, Any]:
    return {
        "fact_id": fact.fact_id,
        "schema_version": fact.schema_version,
        "run_id": fact.run_id,
        "session_id": fact.session_id,
        "request_id": fact.request_id,
        "user_id": fact.user_id,
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


def build_records_for_builder(
    *,
    builder: str,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
) -> list[dict[str, Any]]:
    """Build in-memory records for one builder."""

    canonical_builder = _canonical_builder(builder)
    if canonical_builder == "facts":
        return _build_facts(facts)
    if canonical_builder == "sft":
        return _build_sft(facts)
    if canonical_builder == "preference":
        return _build_preference(facts, artifacts)
    if canonical_builder == "binary_rl":
        return _build_binary_rl(facts, artifacts)
    raise ValueError(f"unsupported builder: {builder}")


def plan_dataset_export(
    *,
    store_uri: str,
    builder: str,
    session: str,
    run_id: str | None = None,
    out: Path | None = None,
) -> ExportPlan:
    """Plan an export and return predicted records plus manifest metadata."""

    store = SQLiteFactStore(store_uri)
    session_id = (
        None
        if session == "latest" and run_id is not None
        else store.get_latest_session_id() if session == "latest" else session
    )
    if session_id is None and run_id is None:
        raise ValueError("no sessions found in store")

    facts = store.list_facts(session_id=session_id, run_id=run_id)
    if not facts:
        raise ValueError("no facts found in scope")
    artifacts = store.list_artifacts(session_id=session_id, run_id=run_id, latest_only=True)
    canonical_builder = _canonical_builder(builder)
    records = build_records_for_builder(
        builder=canonical_builder,
        facts=facts,
        artifacts=artifacts,
    )
    blockers = _blockers_for_builder(
        builder=canonical_builder,
        facts=facts,
        artifacts=artifacts,
        records=records,
    )
    manifest = _build_manifest(
        builder=canonical_builder,
        session_id=session_id,
        facts=facts,
        artifacts=artifacts,
        record_count=len(records),
        blockers=blockers,
        output_path=out,
        run_id=run_id,
    )
    return ExportPlan(
        builder=canonical_builder,
        session_id=facts[0].session_id,
        run_id=run_id,
        output_path=str(out) if out is not None else None,
        record_count=len(records),
        blockers=blockers,
        manifest=manifest,
        records=records,
    )


def export_dataset(
    *,
    store_uri: str,
    builder: str,
    session: str,
    out: Path,
    run_id: str | None = None,
) -> int:
    """Export a dataset from the stored facts and artifacts for a session."""

    plan = plan_dataset_export(
        store_uri=store_uri,
        builder=builder,
        session=session,
        run_id=run_id,
        out=out,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for record in plan.records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True))
            handle.write("\n")

    manifest_path = _manifest_path(out)
    manifest_path.write_text(
        json.dumps(plan.manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return plan.record_count


def _build_facts(facts: list[FactEvent]) -> list[dict[str, Any]]:
    return [_fact_to_json(fact) for fact in facts]


def _build_sft(facts: list[FactEvent]) -> list[dict[str, Any]]:
    requests_by_id = {
        fact.fact_id: fact
        for fact in facts
        if fact.kind == "request_started" and fact.actor == "model"
    }

    samples: list[dict[str, Any]] = []
    for fact in facts:
        if fact.kind != "response_finished" or fact.actor != "model":
            continue

        parent_ref = fact.parent_ref
        if parent_ref is None or parent_ref not in requests_by_id:
            continue

        request = requests_by_id[parent_ref]
        request_json = request.payload.get("json")
        if not isinstance(request_json, dict):
            continue

        messages = _extract_prompt_messages(request_json)
        message = _extract_assistant_message(fact.payload)
        if messages is None or message is None:
            continue

        sample_messages = list(messages)
        sample_messages.append(message)
        samples.append(
            {
                "session_id": fact.session_id,
                "request_fact_id": request.fact_id,
                "response_fact_id": fact.fact_id,
                "messages": sample_messages,
                "lineage": {
                    "builder": "sft",
                    "fact_ids": [request.fact_id, fact.fact_id],
                    "request_id": request.request_id,
                },
            }
        )

    return samples


def _build_preference(
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
) -> list[dict[str, Any]]:
    branch_summaries = build_branch_inspect_summaries(facts)
    branch_by_id = {branch.branch_id: branch for branch in branch_summaries}
    records: list[dict[str, Any]] = []

    active_preference_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.status == "active" and artifact.artifact_type in _PREFERENCE_ARTIFACT_TYPES
    ]
    for artifact in active_preference_artifacts:
        records.extend(_preference_records_from_artifact(artifact, branch_by_id))

    if records:
        return records

    for pair in build_comparable_branch_pairs(branch_summaries):
        chosen = branch_by_id[pair.chosen_branch_id]
        rejected = branch_by_id[pair.rejected_branch_id]
        records.append(
            {
                "session_id": facts[0].session_id,
                "chosen": {
                    "branch_id": chosen.branch_id,
                    "request_ids": chosen.request_ids,
                },
                "rejected": {
                    "branch_id": rejected.branch_id,
                    "request_ids": rejected.request_ids,
                },
                "source": pair.source,
                "lineage": {
                    "builder": "preference",
                    "source_branch_ids": [chosen.branch_id, rejected.branch_id],
                    "artifact_id": None,
                },
            }
        )
    return records


def _build_binary_rl(
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
) -> list[dict[str, Any]]:
    facts_by_id = {fact.fact_id: fact for fact in facts}
    branch_summaries = build_branch_inspect_summaries(facts)
    branch_by_id = {branch.branch_id: branch for branch in branch_summaries}
    records: list[dict[str, Any]] = []

    for artifact in artifacts:
        if artifact.status != "active" or artifact.artifact_type not in _BINARY_RL_ARTIFACT_TYPES:
            continue
        reward = _reward_from_artifact_payload(artifact.payload)
        if reward is None:
            continue

        target_type, target_id = _split_target_ref(artifact.target_ref)
        target: dict[str, Any]
        if target_type == "fact" and target_id in facts_by_id:
            fact = facts_by_id[target_id]
            target = {
                "type": "fact",
                "fact_id": fact.fact_id,
                "request_id": fact.request_id,
                "kind": fact.kind,
                "actor": fact.actor,
            }
        elif target_type == "branch" and target_id in branch_by_id:
            branch = branch_by_id[target_id]
            target = {
                "type": "branch",
                "branch_id": branch.branch_id,
                "request_ids": branch.request_ids,
                "status": branch.status,
            }
        else:
            target = {
                "type": target_type or "session",
                "target_ref": artifact.target_ref,
            }

        records.append(
            {
                "session_id": facts[0].session_id,
                "target": target,
                "reward": reward,
                "artifact_type": artifact.artifact_type,
                "confidence": artifact.confidence,
                "lineage": {
                    "builder": "binary_rl",
                    "artifact_id": artifact.artifact_id,
                    "target_ref": artifact.target_ref,
                },
            }
        )

    return records


def _blockers_for_builder(
    *,
    builder: str,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
    records: list[dict[str, Any]],
) -> list[str]:
    if builder == "facts":
        return [] if facts else ["no facts found"]
    if builder == "sft":
        return [] if records else ["no successful model response pairs found for SFT"]
    if builder == "preference":
        active_preference_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.status == "active" and artifact.artifact_type in _PREFERENCE_ARTIFACT_TYPES
        ]
        if records:
            return []
        if active_preference_artifacts:
            return ["active preference artifacts did not resolve to known branches"]
        return ["no active preference artifacts or comparable related branch pairs found"]
    if builder == "binary_rl":
        active_binary_rl_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.status == "active" and artifact.artifact_type in _BINARY_RL_ARTIFACT_TYPES
        ]
        if records:
            return []
        if active_binary_rl_artifacts:
            return ["active binary RL artifacts did not contain numeric rewards"]
        return ["no active score/reward artifacts found for binary RL"]
    raise ValueError(f"unsupported builder: {builder}")


def _preference_records_from_artifact(
    artifact: ArtifactRecord,
    branch_by_id: dict[str, Any],
) -> list[dict[str, Any]]:
    payload = artifact.payload
    if artifact.artifact_type == "ranking":
        ordered = payload.get("ordered") or payload.get("ranking")
        if not isinstance(ordered, list):
            return []
        branch_ids = [branch_id for branch_id in ordered if isinstance(branch_id, str)]
        if len(branch_ids) < 2:
            return []
        chosen_id = branch_ids[0]
        return [
            _make_preference_record(
                artifact=artifact,
                chosen_branch_id=chosen_id,
                rejected_branch_id=rejected_id,
                branch_by_id=branch_by_id,
            )
            for rejected_id in branch_ids[1:]
            if rejected_id in branch_by_id and chosen_id in branch_by_id
        ]

    chosen_id = _string_value(payload.get("chosen") or payload.get("chosen_branch_id"))
    rejected_id = _string_value(payload.get("rejected") or payload.get("rejected_branch_id"))
    if chosen_id is None or rejected_id is None:
        return []
    if chosen_id not in branch_by_id or rejected_id not in branch_by_id:
        return []
    return [
        _make_preference_record(
            artifact=artifact,
            chosen_branch_id=chosen_id,
            rejected_branch_id=rejected_id,
            branch_by_id=branch_by_id,
        )
    ]


def _make_preference_record(
    *,
    artifact: ArtifactRecord,
    chosen_branch_id: str,
    rejected_branch_id: str,
    branch_by_id: dict[str, Any],
) -> dict[str, Any]:
    chosen = branch_by_id[chosen_branch_id]
    rejected = branch_by_id[rejected_branch_id]
    return {
        "session_id": artifact.session_id,
        "chosen": {
            "branch_id": chosen.branch_id,
            "request_ids": chosen.request_ids,
            "status": chosen.status,
        },
        "rejected": {
            "branch_id": rejected.branch_id,
            "request_ids": rejected.request_ids,
            "status": rejected.status,
        },
        "source": artifact.artifact_type,
        "lineage": {
            "builder": "preference",
            "artifact_id": artifact.artifact_id,
            "target_ref": artifact.target_ref,
        },
    }


def _reward_from_artifact_payload(payload: dict[str, Any]) -> float | int | None:
    for key in ("reward", "score", "value"):
        value = payload.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    label = payload.get("label")
    if isinstance(label, bool):
        return 1 if label else 0
    if isinstance(label, int):
        return label
    return None


def _canonical_builder(builder: str) -> str:
    if builder == "binary-rl":
        return "binary_rl"
    return builder


def _split_target_ref(target_ref: str) -> tuple[str | None, str]:
    if ":" not in target_ref:
        return None, target_ref
    prefix, value = target_ref.split(":", 1)
    return prefix, value


def _manifest_path(out: Path) -> Path:
    return out.with_name(f"{out.name}.manifest.json")


def _build_manifest(
    *,
    builder: str,
    session_id: str,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
    record_count: int,
    blockers: list[str],
    output_path: Path | None,
    run_id: str | None,
) -> dict[str, Any]:
    return {
        "builder": builder,
        "created_at": datetime.now(UTC).isoformat(),
        "session_id": session_id,
        "run_id": run_id,
        "record_count": record_count,
        "ready": not blockers and record_count > 0,
        "blockers": blockers,
        "output_path": str(output_path) if output_path is not None else None,
        "source_run_ids": sorted({fact.run_id for fact in facts}),
        "fact_count": len(facts),
        "artifact_count": len(artifacts),
        "artifact_ids": [artifact.artifact_id for artifact in artifacts],
    }


def _extract_prompt_messages(request_json: dict[str, Any]) -> list[dict[str, Any]] | None:
    messages = request_json.get("messages")
    if isinstance(messages, list):
        normalized = _normalize_messages(messages)
        return normalized if normalized else None

    input_value = request_json.get("input")
    if isinstance(input_value, str):
        return [{"role": "user", "content": input_value}]
    if isinstance(input_value, dict):
        normalized = _normalize_messages([input_value])
        return normalized if normalized else None
    if isinstance(input_value, list):
        normalized = _normalize_messages(input_value)
        return normalized if normalized else None
    return None


def _extract_assistant_message(response_payload: dict[str, Any]) -> dict[str, Any] | None:
    canonical = response_payload.get("canonical")
    if isinstance(canonical, dict):
        canonical_message = _normalize_assistant_message(canonical.get("assistant_message"))
        if canonical_message is not None:
            return canonical_message

    response_json = response_payload.get("json")
    if not isinstance(response_json, dict):
        return None

    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = first_choice.get("message")
            if isinstance(message, dict):
                normalized = _normalize_assistant_message(message)
                if normalized is not None:
                    return normalized

    output_text = response_json.get("output_text")
    if isinstance(output_text, str) and output_text:
        return {"role": "assistant", "content": output_text}
    if isinstance(output_text, list):
        combined_output_text = "\n".join(
            text for text in output_text if isinstance(text, str) and text
        )
        if combined_output_text:
            return {"role": "assistant", "content": combined_output_text}

    output_items = response_json.get("output")
    if isinstance(output_items, list):
        normalized = _normalize_responses_assistant_message(output_items)
        if normalized is not None:
            return normalized
    return None


def _normalize_messages(items: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if not isinstance(role, str) or not role:
            continue
        content = _normalize_content(item.get("content"))
        if content is None:
            continue
        normalized.append({"role": role, "content": content})
    return normalized


def _normalize_assistant_message(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    role = value.get("role")
    normalized_role = role if isinstance(role, str) and role else "assistant"
    content = _normalize_content(value.get("content"))
    tool_calls = _normalize_tool_calls(value.get("tool_calls"))
    if content is None and not tool_calls:
        return None
    message: dict[str, Any] = {"role": normalized_role}
    if content is not None:
        message["content"] = content
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _normalize_responses_assistant_message(output_items: list[Any]) -> dict[str, Any] | None:
    content = None
    tool_calls: list[dict[str, Any]] = []
    for item in output_items:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in {None, "message"} and content is None:
            text = _normalize_content(item.get("content"))
            if text is not None:
                content = text
        elif item_type == "function_call":
            tool_calls.append(
                {
                    "id": _string_value(item.get("id")),
                    "type": "function",
                    "function": {
                        "name": _string_value(item.get("name")) or "",
                        "arguments": _normalize_content(item.get("arguments")) or "",
                    },
                    **(
                        {"call_id": _string_value(item.get("call_id"))}
                        if _string_value(item.get("call_id")) is not None
                        else {}
                    ),
                }
            )
    if content is None and not tool_calls:
        return None
    message: dict[str, Any] = {"role": "assistant"}
    if content is not None:
        message["content"] = content
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _normalize_tool_calls(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        if not isinstance(function, dict):
            continue
        normalized.append(
            {
                "id": _string_value(item.get("id")),
                "type": _string_value(item.get("type")) or "function",
                "function": {
                    "name": _string_value(function.get("name")) or "",
                    "arguments": _normalize_content(function.get("arguments")) or "",
                },
                **(
                    {"call_id": _string_value(item.get("call_id"))}
                    if _string_value(item.get("call_id")) is not None
                    else {}
                ),
            }
        )
    return normalized


def _normalize_content(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "content"):
            nested = _normalize_content(value.get(key))
            if nested is not None:
                return nested
        return None
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            text = None
            if isinstance(item, dict):
                text = _normalize_content(
                    item.get("text")
                    or item.get("content")
                    or item.get("value")
                )
            elif isinstance(item, str):
                text = item
            if text:
                parts.append(text)
        if parts:
            return "\n".join(parts)
    return None


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
