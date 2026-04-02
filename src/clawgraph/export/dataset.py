"""Dataset export helpers for ClawGraph."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from clawgraph.artifacts import annotate_records_with_e1, summarize_e1_annotations
from clawgraph.builders import BuildContext, get_dataset_builder, register_dataset_builder
from clawgraph.graph import (
    build_branch_inspect_summaries,
    build_comparable_branch_pairs,
    correlate_request_groups,
    infer_branches,
    partition_facts_by_run,
)
from clawgraph.protocol.factories import new_dataset_snapshot_record
from clawgraph.protocol.models import ArtifactRecord, CohortMemberRecord, CohortRecord, FactEvent
from clawgraph.protocol.semantics import extract_prompt_messages
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
_BUILTIN_BUILDERS_REGISTERED = False


@dataclass(slots=True)
class ExportPlan:
    """Planned dataset export including preview information."""

    builder: str
    session_id: str
    run_id: str | None
    cohort_id: str | None
    dataset_recipe_id: str
    dataset_snapshot_id: str
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


@dataclass(slots=True)
class _BuiltinDatasetBuilder:
    """Adapter for one built-in dataset builder."""

    name: str
    build_fn: Callable[[list[FactEvent], list[ArtifactRecord]], list[dict[str, Any]]]
    blocker_fn: Callable[[list[FactEvent], list[ArtifactRecord], list[dict[str, Any]]], list[str]]
    aliases: tuple[str, ...] = ()

    def build_records(
        self,
        *,
        facts: list[FactEvent],
        artifacts: list[ArtifactRecord],
        context: BuildContext | None = None,
    ) -> list[dict[str, Any]]:
        del context
        return self.build_fn(facts, artifacts)

    def blockers(
        self,
        *,
        facts: list[FactEvent],
        artifacts: list[ArtifactRecord],
        records: list[dict[str, Any]],
        context: BuildContext | None = None,
    ) -> list[str]:
        del context
        return self.blocker_fn(facts, artifacts, records)


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


def _build_request_records_by_fact_id(
    facts: list[FactEvent],
) -> dict[str, dict[str, Any]]:
    """Build reusable request-centric records from captured facts."""

    groups = correlate_request_groups(facts)
    _, request_branch_map = infer_branches(groups, facts=facts)
    records: dict[str, dict[str, Any]] = {}

    for group in groups:
        request = group.request
        request_json = request.payload.get("json")
        input_messages = _request_input_messages(request.payload)
        output_message = (
            _extract_assistant_message(group.response.payload)
            if group.response is not None
            else None
        )

        record: dict[str, Any] = {
            "session_id": request.session_id,
            "run_id": request.run_id,
            "request_id": request.request_id or request.fact_id,
            "request_fact_id": request.fact_id,
            "actor": request.actor,
            "path": group.path,
            "branch_id": request_branch_map.get(request.fact_id),
            "outcome": group.outcome,
        }
        if input_messages:
            record["input_messages"] = list(input_messages)
            record["messages"] = list(input_messages)
        if output_message is not None:
            record["output_message"] = output_message
            record["messages"] = [*(record.get("messages") or []), output_message]
        if request_json is not None:
            record["request_payload"] = request_json
        response_record = (
            _response_record(group.response.payload) if group.response is not None else None
        )
        if response_record is not None:
            record["response"] = response_record
            record["response_fact_id"] = group.response.fact_id
        error_record = _error_record(group.error.payload) if group.error is not None else None
        if error_record is not None:
            record["error"] = error_record
            record["error_fact_id"] = group.error.fact_id
        records[request.fact_id] = record

    return records


def _build_branch_records_by_key(
    facts: list[FactEvent],
) -> tuple[list[Any], dict[tuple[str, str], dict[str, Any]]]:
    """Build branch-level self-contained trajectories keyed by run and branch id."""

    branch_summaries = build_branch_inspect_summaries(facts)
    request_records_by_fact_id = _build_request_records_by_fact_id(facts)
    run_session_map = _run_session_map(facts)
    branch_records: dict[tuple[str, str], dict[str, Any]] = {}

    for branch in branch_summaries:
        steps = [
            request_records_by_fact_id[request_fact_id]
            for request_fact_id in branch.request_fact_ids
            if request_fact_id in request_records_by_fact_id
        ]
        branch_records[(branch.run_id, branch.branch_id)] = {
            "session_id": run_session_map.get(branch.run_id),
            "run_id": branch.run_id,
            "branch_id": branch.branch_id,
            "branch_type": branch.branch_type,
            "status": branch.status,
            "source": branch.source,
            "parent_branch_id": branch.parent_branch_id,
            "request_ids": list(branch.request_ids),
            "request_fact_ids": list(branch.request_fact_ids),
            "prompt": _branch_prompt(steps),
            "trajectory": steps,
            "terminal_output": _terminal_output(steps),
        }

    return branch_summaries, branch_records


def _build_run_records(
    facts: list[FactEvent],
    *,
    request_records_by_fact_id: dict[str, dict[str, Any]],
    branch_records_by_key: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build run-scoped records for session-level supervision targets."""

    run_records: dict[str, dict[str, Any]] = {}
    for run_id, run_facts in partition_facts_by_run(facts):
        request_steps = [
            request_records_by_fact_id[fact.fact_id]
            for fact in run_facts
            if fact.kind == "request_started" and fact.fact_id in request_records_by_fact_id
        ]
        branch_steps = [
            branch_record
            for (branch_run_id, _), branch_record in branch_records_by_key.items()
            if branch_run_id == run_id
        ]
        run_records[run_id] = {
            "session_id": run_facts[0].session_id,
            "run_id": run_id,
            "prompt": _first_non_empty_prompt(request_steps, branch_steps),
            "requests": request_steps,
            "branches": branch_steps,
        }
    return run_records


def _response_record(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Build a compact response record that remains training-usable."""

    record: dict[str, Any] = {}
    for key in (
        "status_code",
        "content_type",
        "streamed",
        "stream_complete",
        "client_disconnected",
        "chunk_count",
        "ttfb_ms",
        "total_latency_ms",
        "stream_duration_ms",
    ):
        if key in payload:
            record[key] = payload[key]
    assistant_message = _extract_assistant_message(payload)
    if assistant_message is not None:
        record["assistant_message"] = assistant_message
    elif "canonical" in payload:
        record["canonical"] = payload["canonical"]
    elif "json" in payload:
        record["json"] = payload["json"]
    elif "text" in payload:
        record["text"] = payload["text"]
    elif "preview" in payload:
        record["preview"] = payload["preview"]
    return record or None


def _error_record(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Build a compact error record."""

    record: dict[str, Any] = {}
    for key in ("status_code", "error", "error_code", "content_type", "ttfb_ms", "total_latency_ms"):
        if key in payload:
            record[key] = payload[key]
    if "json" in payload:
        record["json"] = payload["json"]
    elif "text" in payload:
        record["text"] = payload["text"]
    return record or None


def _branch_prompt(steps: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Return the first prompt found within a branch trajectory."""

    for step in steps:
        prompt = step.get("input_messages")
        if isinstance(prompt, list) and prompt:
            return prompt
    return None


def _terminal_output(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the terminal supervision-relevant output for a trajectory."""

    for step in reversed(steps):
        output_message = step.get("output_message")
        if isinstance(output_message, dict):
            return {"type": "assistant_message", "message": output_message}
        response = step.get("response")
        if isinstance(response, dict):
            return {"type": "response", "response": response}
        error = step.get("error")
        if isinstance(error, dict):
            return {"type": "error", "error": error}
    return None


def _first_non_empty_prompt(
    request_steps: list[dict[str, Any]],
    branch_steps: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Return the first prompt available inside a run."""

    for step in request_steps:
        prompt = step.get("input_messages")
        if isinstance(prompt, list) and prompt:
            return prompt
    for branch in branch_steps:
        prompt = branch.get("prompt")
        if isinstance(prompt, list) and prompt:
            return prompt
    return None


def _shared_prompt(
    chosen: dict[str, Any],
    rejected: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Return a shared prompt when both preference sides refer to the same prompt."""

    chosen_prompt = chosen.get("prompt")
    rejected_prompt = rejected.get("prompt")
    if isinstance(chosen_prompt, list) and chosen_prompt == rejected_prompt:
        return chosen_prompt
    if isinstance(chosen_prompt, list) and rejected_prompt is None:
        return chosen_prompt
    if isinstance(rejected_prompt, list) and chosen_prompt is None:
        return rejected_prompt
    return None


def _prompts_conflict(chosen: dict[str, Any], rejected: dict[str, Any]) -> bool:
    chosen_prompt = chosen.get("prompt")
    rejected_prompt = rejected.get("prompt")
    return (
        isinstance(chosen_prompt, list)
        and isinstance(rejected_prompt, list)
        and chosen_prompt != rejected_prompt
    )


def _resolve_branch_key(
    *,
    branch_id: str,
    run_id: str | None,
    branch_records_by_key: dict[tuple[str, str], dict[str, Any]],
) -> tuple[str, str] | None:
    """Resolve a branch id with optional run scoping."""

    if run_id is not None and (run_id, branch_id) in branch_records_by_key:
        return run_id, branch_id
    matches = [key for key in branch_records_by_key if key[1] == branch_id]
    if len(matches) == 1:
        return matches[0]
    return None


def _build_context(
    *,
    facts: list[FactEvent],
    builder: str,
    run_id: str | None = None,
) -> BuildContext:
    resolved_run_id = run_id
    if resolved_run_id is None:
        run_ids = sorted({fact.run_id for fact in facts})
        resolved_run_id = run_ids[0] if len(run_ids) == 1 else None
    resolved_session_id = _single_session_id(facts)
    return BuildContext(
        session_id=resolved_session_id,
        run_id=resolved_run_id,
        selection_query={
            "builder": builder,
            "session_id": resolved_session_id,
            "run_id": resolved_run_id,
        },
    )


def _sample_unit_for_builder(builder: str) -> str:
    if builder == "sft":
        return "request"
    if builder == "preference":
        return "branch"
    if builder == "binary_rl":
        return "run"
    return "fact"


def _dataset_recipe_id(builder: str) -> str:
    return f"clawgraph.recipe.{builder}.v1"


def _fallback_split_guard_key(record: dict[str, Any]) -> str:
    for key in ("task_instance_key", "run_id", "session_id", "request_id", "fact_id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return f"{key}:{value}"
    target = record.get("target")
    if isinstance(target, dict):
        for key in ("run_id", "branch_id", "fact_id", "target_ref"):
            value = target.get(key)
            if isinstance(value, str) and value:
                return f"target.{key}:{value}"
    lineage = record.get("lineage")
    if isinstance(lineage, dict):
        for key in ("request_id", "artifact_id", "target_ref"):
            value = lineage.get(key)
            if isinstance(value, str) and value:
                return f"lineage.{key}:{value}"
    return hashlib.sha256(
        json.dumps(record, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _hash_split(guard_key: str) -> str:
    bucket = int(hashlib.sha256(guard_key.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "val"
    return "test"


def _canonical_record_hash(record: dict[str, Any]) -> str:
    canonical = {
        "builder": record.get("lineage", {}).get("builder"),
        "task_type": record.get("task_type"),
        "task_instance_key": record.get("task_instance_key"),
        "task_template_hash": record.get("annotation", {}).get("task_template_hash"),
        "prompt": record.get("prompt"),
        "messages": record.get("messages"),
        "completion": record.get("completion"),
        "chosen": record.get("chosen"),
        "rejected": record.get("rejected"),
        "target": record.get("target"),
        "reward": record.get("reward"),
    }
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _dedupe_records(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    duplicates_removed = 0
    near_duplicate_clusters = _distribution_from_records(
        [record for record in records if isinstance(record.get("annotation"), dict)],
        "task_template_hash",
    )
    for record in records:
        canonical_hash = _canonical_record_hash(record)
        if canonical_hash in seen:
            duplicates_removed += 1
            continue
        seen.add(canonical_hash)
        record_copy = dict(record)
        record_copy["canonical_record_hash"] = canonical_hash
        deduped.append(record_copy)
    return deduped, {
        "rule_version": "clawgraph.exact_dedupe.v1",
        "input_records": len(records),
        "output_records": len(deduped),
        "duplicates_removed": duplicates_removed,
        "near_duplicate_cluster_key": "task_template_hash",
        "near_duplicate_clusters": near_duplicate_clusters,
    }


def _run_time_range(facts: list[FactEvent]) -> dict[str, tuple[str, str]]:
    per_run: dict[str, list[str]] = {}
    for fact in facts:
        per_run.setdefault(fact.run_id, []).append(fact.timestamp.isoformat())
    return {
        run_id: (min(timestamps), max(timestamps))
        for run_id, timestamps in per_run.items()
        if timestamps
    }


def _cohort_split_assignments(
    *,
    members: list[CohortMemberRecord],
    facts: list[FactEvent],
) -> tuple[dict[str, tuple[str, str]], dict[str, Any]]:
    run_time_bounds = _run_time_range(facts)
    strata: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for member in members:
        task_type = str(member.metadata.get("task_type") or "unknown")
        stratum_key = (member.slice_id, task_type)
        instance_key = member.task_instance_key
        instance_group = strata.setdefault(stratum_key, {}).setdefault(
            instance_key,
            {
                "task_instance_key": instance_key,
                "run_ids": [],
                "latest_timestamp": run_time_bounds.get(member.run_id, ("", ""))[1],
            },
        )
        instance_group["run_ids"].append(member.run_id)
        latest = run_time_bounds.get(member.run_id, ("", ""))[1]
        if latest > instance_group["latest_timestamp"]:
            instance_group["latest_timestamp"] = latest

    assignments: dict[str, tuple[str, str]] = {}
    split_counts = {"train": 0, "val": 0, "test": 0}
    leakage_keys: set[str] = set()
    temporal_strata: list[dict[str, Any]] = []
    for stratum_key, instance_groups in strata.items():
        ordered_groups = sorted(
            instance_groups.values(),
            key=lambda group: (group["latest_timestamp"], group["task_instance_key"]),
        )
        if len(ordered_groups) >= 10:
            test_count = max(1, round(len(ordered_groups) * 0.1))
            val_count = max(1, round(len(ordered_groups) * 0.1))
            train_cutoff = len(ordered_groups) - test_count - val_count
            for index, group in enumerate(ordered_groups):
                if index < train_cutoff:
                    split = "train"
                elif index < len(ordered_groups) - test_count:
                    split = "val"
                else:
                    split = "test"
                for run_id in group["run_ids"]:
                    assignments[run_id] = (split, group["task_instance_key"])
                    split_counts[split] += 1
                leakage_keys.add(group["task_instance_key"])
            temporal_strata.append(
                {
                    "slice_id": stratum_key[0],
                    "task_type": stratum_key[1],
                    "assignment_mode": "time_window",
                    "group_count": len(ordered_groups),
                }
            )
            continue

        for group in ordered_groups:
            split = _hash_split(group["task_instance_key"])
            for run_id in group["run_ids"]:
                assignments[run_id] = (split, group["task_instance_key"])
                split_counts[split] += 1
            leakage_keys.add(group["task_instance_key"])
        temporal_strata.append(
            {
                "slice_id": stratum_key[0],
                "task_type": stratum_key[1],
                "assignment_mode": "hash_fallback",
                "group_count": len(ordered_groups),
            }
        )
    return assignments, {
        "rule_version": "clawgraph.cohort_split.v1",
        "distinct_guard_keys": len(leakage_keys),
        "counts": split_counts,
        "strata": temporal_strata,
    }


def _annotate_records_with_dataset_context(
    *,
    records: list[dict[str, Any]],
    builder: str,
    dataset_recipe_id: str,
    dataset_snapshot_id: str,
    cohort_id: str | None,
    cohort_members: list[CohortMemberRecord] | None = None,
    facts: list[FactEvent] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    split_counts = {"train": 0, "val": 0, "test": 0}
    guard_keys: set[str] = set()
    cohort_assignments: dict[str, tuple[str, str]] = {}
    split_metadata = {
        "rule_version": "clawgraph.hash_split.v1",
        "distinct_guard_keys": 0,
        "counts": split_counts,
        "strata": [],
    }
    if cohort_members is not None and facts is not None:
        cohort_assignments, split_manifest = _cohort_split_assignments(
            members=cohort_members,
            facts=facts,
        )
        split_metadata = split_manifest
        guard_keys = {
            assignment[1] for assignment in cohort_assignments.values()
        }
    annotated: list[dict[str, Any]] = []
    for record in records:
        run_id = _record_run_id(record)
        if run_id is not None and run_id in cohort_assignments:
            split, guard_key = cohort_assignments[run_id]
        else:
            guard_key = _fallback_split_guard_key(record)
            split = _hash_split(guard_key)
            guard_keys.add(guard_key)
        record_copy = dict(record)
        record_copy["split"] = split
        record_copy["split_guard_key"] = guard_key
        record_copy["dataset_recipe_id"] = dataset_recipe_id
        record_copy["dataset_snapshot_id"] = dataset_snapshot_id
        if cohort_id is not None:
            record_copy["cohort_id"] = cohort_id
        annotated.append(record_copy)
        split_counts[split] += 1
    split_metadata["counts"] = split_counts
    split_metadata["distinct_guard_keys"] = len(guard_keys)
    return annotated, split_metadata


def _distribution_from_records(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for record in records:
        value = record.get(key)
        if value is None:
            annotation = record.get("annotation")
            if isinstance(annotation, dict):
                value = annotation.get(key)
        if not isinstance(value, str) or not value:
            continue
        distribution[value] = distribution.get(value, 0) + 1
    return distribution


def build_records_for_builder(
    *,
    builder: str,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
) -> list[dict[str, Any]]:
    """Build in-memory records for one builder."""

    _ensure_builtin_builders_registered()
    builder_impl = get_dataset_builder(builder)
    records = list(
        builder_impl.build_records(
            facts=facts,
            artifacts=artifacts,
            context=_build_context(facts=facts, builder=builder_impl.name),
        )
    )
    return annotate_records_with_e1(records=records, facts=facts, artifacts=artifacts)


def _load_cohort_scope(
    *,
    store: SQLiteFactStore,
    cohort_id: str,
) -> tuple[CohortRecord, list[CohortMemberRecord], list[FactEvent], list[ArtifactRecord]]:
    cohort = store.get_cohort(cohort_id)
    if cohort is None:
        raise ValueError(f"cohort not found: {cohort_id}")
    members = store.list_cohort_members(cohort_id)
    if not members:
        raise ValueError(f"cohort has no members: {cohort_id}")

    run_ids = {member.run_id for member in members}
    session_ids = {member.session_id for member in members}
    facts: list[FactEvent] = []
    for run_id in sorted(run_ids):
        facts.extend(store.list_facts(run_id=run_id))
    if not facts:
        raise ValueError(f"no facts found for cohort: {cohort_id}")
    facts.sort(key=lambda fact: (fact.timestamp, fact.fact_id))
    frozen_artifact_ids = sorted(
        {
            artifact_id
            for member in members
            for artifact_id in member.metadata.get("frozen_artifact_ids", [])
            if isinstance(artifact_id, str) and artifact_id
        }
    )
    if frozen_artifact_ids:
        artifacts = store.list_artifacts(artifact_ids=frozen_artifact_ids)
        return cohort, members, facts, artifacts

    fact_ids = {fact.fact_id for fact in facts}
    branch_ids = {
        summary.branch_id
        for summary in build_branch_inspect_summaries(facts)
        if isinstance(summary.branch_id, str) and summary.branch_id
    }
    candidate_artifacts: list[ArtifactRecord] = []
    for session_id in sorted(session_ids):
        candidate_artifacts.extend(
            store.list_artifacts(session_id=session_id, latest_only=False)
        )
    seen_artifact_ids: set[str] = set()
    artifacts: list[ArtifactRecord] = []
    for artifact in candidate_artifacts:
        if artifact.artifact_id in seen_artifact_ids:
            continue
        if cohort.created_at is not None and artifact.created_at is not None:
            if artifact.created_at > cohort.created_at:
                continue
        if not _artifact_in_scope(
            artifact=artifact,
            run_ids=run_ids,
            session_ids=session_ids,
            fact_ids=fact_ids,
            branch_ids=branch_ids,
        ):
            continue
        artifacts.append(artifact)
        seen_artifact_ids.add(artifact.artifact_id)
    return cohort, members, facts, artifacts


def plan_dataset_export(
    *,
    store_uri: str,
    builder: str,
    session: str = "latest",
    run_id: str | None = None,
    out: Path | None = None,
    cohort_id: str | None = None,
) -> ExportPlan:
    """Plan an export and return predicted records plus manifest metadata."""

    store = SQLiteFactStore(store_uri)
    if cohort_id is not None:
        cohort, cohort_members, facts, artifacts = _load_cohort_scope(
            store=store,
            cohort_id=cohort_id,
        )
        return plan_dataset_export_for_scope(
            builder=builder,
            facts=facts,
            artifacts=artifacts,
            out=out,
            run_id=None,
            session_id=f"cohort:{cohort_id}",
            cohort_id=cohort_id,
            cohort=cohort,
            cohort_members=cohort_members,
            legacy_scope=False,
        )
    resolved_run_id = run_id
    resolved_session_id: str | None
    if resolved_run_id is not None:
        resolved_session_id = store.get_session_id_for_run(resolved_run_id)
        if resolved_session_id is None:
            raise ValueError(f"run not found: {resolved_run_id}")
        if session not in {None, "latest"} and session != resolved_session_id:
            raise ValueError(
                f"run {resolved_run_id} belongs to session {resolved_session_id}, not {session}"
            )
    else:
        resolved_session_id = store.get_latest_session_id() if session == "latest" else session
        if resolved_session_id is not None:
            resolved_run_id = store.get_latest_run_id(session_id=resolved_session_id)

    if resolved_session_id is None and resolved_run_id is None:
        raise ValueError("no sessions found in store")

    facts = store.list_facts(session_id=resolved_session_id, run_id=resolved_run_id)
    if not facts:
        raise ValueError("no facts found in scope")
    artifacts = store.list_artifacts(
        session_id=resolved_session_id,
        run_id=resolved_run_id,
        latest_only=True,
    )
    return plan_dataset_export_for_scope(
        builder=builder,
        facts=facts,
        artifacts=artifacts,
        out=out,
        run_id=resolved_run_id,
        session_id=resolved_session_id,
        legacy_scope=True,
    )


def plan_dataset_export_for_scope(
    *,
    builder: str,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
    out: Path | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    cohort_id: str | None = None,
    cohort: CohortRecord | None = None,
    cohort_members: list[CohortMemberRecord] | None = None,
    legacy_scope: bool = False,
) -> ExportPlan:
    """Plan an export directly from facts and artifacts already loaded in memory."""

    if not facts:
        raise ValueError("no facts found in scope")
    effective_session_id = session_id or facts[0].session_id
    _ensure_builtin_builders_registered()
    builder_impl = get_dataset_builder(builder)
    dataset_recipe_id = _dataset_recipe_id(builder_impl.name)
    dataset_snapshot_id = f"ds_{uuid4().hex}"
    raw_records = build_records_for_builder(
        builder=builder_impl.name,
        facts=facts,
        artifacts=artifacts,
    )
    records, dedupe_manifest = _dedupe_records(raw_records)
    records, split_manifest = _annotate_records_with_dataset_context(
        records=records,
        builder=builder_impl.name,
        dataset_recipe_id=dataset_recipe_id,
        dataset_snapshot_id=dataset_snapshot_id,
        cohort_id=cohort_id,
        cohort_members=cohort_members,
        facts=facts,
    )
    blockers = _blockers_for_builder(
        builder=builder_impl.name,
        facts=facts,
        artifacts=artifacts,
        records=records,
        run_id=run_id,
    )
    blockers.extend(
        _scope_contract_blockers(
            builder=builder_impl.name,
            cohort=cohort,
            cohort_members=cohort_members,
            legacy_scope=legacy_scope,
        )
    )
    manifest = _build_manifest(
        builder=builder_impl.name,
        session_id=effective_session_id,
        facts=facts,
        artifacts=artifacts,
        record_count=len(records),
        blockers=blockers,
        output_path=out,
        run_id=run_id,
        cohort_id=cohort_id,
        dataset_recipe_id=dataset_recipe_id,
        dataset_snapshot_id=dataset_snapshot_id,
        sample_unit=_sample_unit_for_builder(builder_impl.name),
        split_manifest=split_manifest,
        dedupe_manifest=dedupe_manifest,
        records=records,
        cohort=cohort,
        legacy_scope=legacy_scope,
    )
    return ExportPlan(
        builder=builder_impl.name,
        session_id=effective_session_id,
        run_id=run_id,
        cohort_id=cohort_id,
        dataset_recipe_id=dataset_recipe_id,
        dataset_snapshot_id=dataset_snapshot_id,
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
    session: str = "latest",
    out: Path,
    run_id: str | None = None,
    cohort_id: str | None = None,
) -> int:
    """Export a dataset from the stored facts and artifacts for a session."""

    plan = plan_dataset_export(
        store_uri=store_uri,
        builder=builder,
        session=session,
        run_id=run_id,
        out=out,
        cohort_id=cohort_id,
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
    store = SQLiteFactStore(store_uri)
    store.append_dataset_snapshot(
        new_dataset_snapshot_record(
            dataset_snapshot_id=plan.dataset_snapshot_id,
            dataset_recipe_id=plan.dataset_recipe_id,
            builder=plan.builder,
            sample_unit=plan.manifest["sample_unit"],
            cohort_id=plan.cohort_id,
            output_path=str(out),
            record_count=plan.record_count,
            manifest=plan.manifest,
            metadata={
                "session_id": plan.session_id,
                "run_id": plan.run_id,
            },
        )
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
        messages = _request_input_messages(request.payload)
        message = _extract_assistant_message(fact.payload)
        if messages is None or message is None:
            continue

        sample_messages = list(messages)
        sample_messages.append(message)
        samples.append(
            {
                "session_id": fact.session_id,
                "run_id": fact.run_id,
                "request_fact_id": request.fact_id,
                "response_fact_id": fact.fact_id,
                "request_id": request.request_id,
                "prompt": list(messages),
                "completion": message,
                "messages": sample_messages,
                "supervision": {"type": "sft"},
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
    branch_summaries, branch_records_by_key = _build_branch_records_by_key(facts)
    records: list[dict[str, Any]] = []

    active_preference_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.status == "active" and artifact.artifact_type in _PREFERENCE_ARTIFACT_TYPES
    ]
    for artifact in active_preference_artifacts:
        records.extend(
            _preference_records_from_artifact(
                artifact,
                branch_records_by_key=branch_records_by_key,
            )
        )

    if records:
        return records

    branch_summaries_by_run: dict[str, list[Any]] = {}
    for summary in branch_summaries:
        branch_summaries_by_run.setdefault(summary.run_id, []).append(summary)

    for run_id, run_branch_summaries in branch_summaries_by_run.items():
        for pair in build_comparable_branch_pairs(run_branch_summaries):
            chosen_key = _resolve_branch_key(
                branch_id=pair.chosen_branch_id,
                run_id=run_id,
                branch_records_by_key=branch_records_by_key,
            )
            rejected_key = _resolve_branch_key(
                branch_id=pair.rejected_branch_id,
                run_id=run_id,
                branch_records_by_key=branch_records_by_key,
            )
            if chosen_key is None or rejected_key is None:
                continue
            record = _make_preference_record(
                artifact=None,
                source=pair.source,
                reason=pair.reason,
                chosen=branch_records_by_key[chosen_key],
                rejected=branch_records_by_key[rejected_key],
            )
            if record is not None:
                records.append(record)
    return records


def _build_binary_rl(
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
) -> list[dict[str, Any]]:
    facts_by_id = {fact.fact_id: fact for fact in facts}
    request_records_by_fact_id = _build_request_records_by_fact_id(facts)
    _, branch_records_by_key = _build_branch_records_by_key(facts)
    run_session_map = _run_session_map(facts)
    run_records = _build_run_records(
        facts,
        request_records_by_fact_id=request_records_by_fact_id,
        branch_records_by_key=branch_records_by_key,
    )
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
            request_record: dict[str, Any] | None = None
            if fact.kind == "request_started":
                request_record = request_records_by_fact_id.get(fact.fact_id)
            elif fact.parent_ref is not None:
                request_record = request_records_by_fact_id.get(fact.parent_ref)
            target = {
                "type": "fact",
                "fact_id": fact.fact_id,
                "request_id": fact.request_id,
                "run_id": fact.run_id,
                "kind": fact.kind,
                "actor": fact.actor,
                **({"trajectory": request_record} if request_record is not None else {}),
            }
        elif target_type == "branch":
            branch_key = _resolve_branch_key(
                branch_id=target_id,
                run_id=artifact.run_id,
                branch_records_by_key=branch_records_by_key,
            )
            if branch_key is None:
                target = {
                    "type": "branch",
                    "target_ref": artifact.target_ref,
                }
            else:
                branch = branch_records_by_key[branch_key]
                target = {
                    "type": "branch",
                    "branch_id": branch["branch_id"],
                    "run_id": branch["run_id"],
                    "request_ids": branch["request_ids"],
                    "status": branch["status"],
                    "trajectory": branch["trajectory"],
                    "prompt": branch["prompt"],
                    "terminal_output": branch["terminal_output"],
                }
        elif target_type == "run":
            resolved_run_id = artifact.run_id or target_id
            if resolved_run_id in run_records:
                run_record = run_records[resolved_run_id]
                target = {
                    "type": "run",
                    "run_id": run_record["run_id"],
                    "prompt": run_record["prompt"],
                    "requests": run_record["requests"],
                    "branches": run_record["branches"],
                }
            else:
                target = {
                    "type": "run",
                    "target_ref": artifact.target_ref,
                }
        elif target_type in {None, "session"} and artifact.run_id in run_records:
            run_record = run_records[artifact.run_id]
            target = {
                "type": "run",
                "run_id": run_record["run_id"],
                "prompt": run_record["prompt"],
                "requests": run_record["requests"],
                "branches": run_record["branches"],
            }
        else:
            target = {
                "type": target_type or "session",
                "target_ref": artifact.target_ref,
            }

        records.append(
            {
                "session_id": artifact.session_id
                or (run_session_map.get(artifact.run_id) if artifact.run_id is not None else None)
                or _single_session_id(facts),
                "run_id": artifact.run_id,
                "target": target,
                "reward": reward,
                "artifact_type": artifact.artifact_type,
                "confidence": artifact.confidence,
                "supervision": {
                    "type": "binary_rl",
                    "artifact_type": artifact.artifact_type,
                    "reward": reward,
                    "confidence": artifact.confidence,
                    "payload": artifact.payload,
                },
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
    run_id: str | None = None,
) -> list[str]:
    _ensure_builtin_builders_registered()
    builder_impl = get_dataset_builder(builder)
    return list(
        builder_impl.blockers(
            facts=facts,
            artifacts=artifacts,
            records=records,
            context=_build_context(
                facts=facts,
                builder=builder_impl.name,
                run_id=run_id,
            ),
        )
    )


def _builtin_blockers_for_builder(
    builder: str,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
    records: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if builder in {"sft", "preference", "binary_rl"}:
        annotation_summary = summarize_e1_annotations(facts=facts, artifacts=artifacts)
        for run_id, run_summary in annotation_summary["runs"].items():
            if run_summary["missing_fields"]:
                blockers.append(
                    f"run {run_id} missing E1 annotations: {', '.join(run_summary['missing_fields'])}"
                )
    if builder == "facts":
        return [] if facts else ["no facts found"]
    if builder == "sft":
        if not records:
            blockers.append("no successful model response pairs found for SFT")
        return blockers
    if builder == "preference":
        active_preference_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.status == "active" and artifact.artifact_type in _PREFERENCE_ARTIFACT_TYPES
        ]
        if records and not blockers:
            return []
        if active_preference_artifacts:
            blockers.append("active preference artifacts did not resolve to known branches")
            return blockers
        blockers.append("no active preference artifacts or comparable related branch pairs found")
        return blockers
    if builder == "binary_rl":
        active_binary_rl_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.status == "active" and artifact.artifact_type in _BINARY_RL_ARTIFACT_TYPES
        ]
        if records and not blockers:
            return []
        if active_binary_rl_artifacts:
            blockers.append("active binary RL artifacts did not contain numeric rewards")
            return blockers
        blockers.append("no active score/reward artifacts found for binary RL")
        return blockers
    raise ValueError(f"unsupported builder: {builder}")


def _ensure_builtin_builders_registered() -> None:
    global _BUILTIN_BUILDERS_REGISTERED
    if _BUILTIN_BUILDERS_REGISTERED:
        return

    builtin_builders = (
        _BuiltinDatasetBuilder(
            name="facts",
            build_fn=lambda facts, artifacts: _build_facts(facts),
            blocker_fn=lambda facts, artifacts, records: _builtin_blockers_for_builder(
                "facts",
                facts,
                artifacts,
                records,
            ),
        ),
        _BuiltinDatasetBuilder(
            name="sft",
            build_fn=lambda facts, artifacts: _build_sft(facts),
            blocker_fn=lambda facts, artifacts, records: _builtin_blockers_for_builder(
                "sft",
                facts,
                artifacts,
                records,
            ),
        ),
        _BuiltinDatasetBuilder(
            name="preference",
            build_fn=_build_preference,
            blocker_fn=lambda facts, artifacts, records: _builtin_blockers_for_builder(
                "preference",
                facts,
                artifacts,
                records,
            ),
        ),
        _BuiltinDatasetBuilder(
            name="binary_rl",
            aliases=("binary-rl",),
            build_fn=_build_binary_rl,
            blocker_fn=lambda facts, artifacts, records: _builtin_blockers_for_builder(
                "binary_rl",
                facts,
                artifacts,
                records,
            ),
        ),
    )
    for builder in builtin_builders:
        register_dataset_builder(builder)
    _BUILTIN_BUILDERS_REGISTERED = True


def _preference_records_from_artifact(
    artifact: ArtifactRecord,
    *,
    branch_records_by_key: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    payload = artifact.payload
    if artifact.artifact_type == "ranking":
        ordered = payload.get("ordered") or payload.get("ranking")
        if not isinstance(ordered, list):
            return []
        branch_ids = [branch_id for branch_id in ordered if isinstance(branch_id, str)]
        if len(branch_ids) < 2:
            return []
        chosen_key = _resolve_branch_key(
            branch_id=branch_ids[0],
            run_id=artifact.run_id,
            branch_records_by_key=branch_records_by_key,
        )
        if chosen_key is None:
            return []
        records: list[dict[str, Any]] = []
        for rejected_id in branch_ids[1:]:
            rejected_key = _resolve_branch_key(
                branch_id=rejected_id,
                run_id=artifact.run_id,
                branch_records_by_key=branch_records_by_key,
            )
            if rejected_key is None:
                continue
            record = _make_preference_record(
                artifact=artifact,
                source=artifact.artifact_type,
                reason=_string_value(payload.get("reason")),
                chosen=branch_records_by_key[chosen_key],
                rejected=branch_records_by_key[rejected_key],
            )
            if record is not None:
                records.append(record)
        return records

    chosen_id = _string_value(payload.get("chosen") or payload.get("chosen_branch_id"))
    rejected_id = _string_value(payload.get("rejected") or payload.get("rejected_branch_id"))
    if chosen_id is None or rejected_id is None:
        return []
    chosen_key = _resolve_branch_key(
        branch_id=chosen_id,
        run_id=artifact.run_id,
        branch_records_by_key=branch_records_by_key,
    )
    rejected_key = _resolve_branch_key(
        branch_id=rejected_id,
        run_id=artifact.run_id,
        branch_records_by_key=branch_records_by_key,
    )
    if chosen_key is None or rejected_key is None:
        return []
    record = _make_preference_record(
        artifact=artifact,
        source=artifact.artifact_type,
        reason=_string_value(payload.get("reason")),
        chosen=branch_records_by_key[chosen_key],
        rejected=branch_records_by_key[rejected_key],
    )
    return [record] if record is not None else []


def _make_preference_record(
    *,
    artifact: ArtifactRecord | None,
    source: str,
    reason: str | None,
    chosen: dict[str, Any],
    rejected: dict[str, Any],
) -> dict[str, Any] | None:
    shared_prompt = _shared_prompt(chosen, rejected)
    allow_prompt_mismatch = bool(
        artifact is not None and artifact.payload.get("allow_prompt_mismatch")
    )
    if _prompts_conflict(chosen, rejected) and not allow_prompt_mismatch:
        return None
    return {
        "session_id": chosen["session_id"],
        "run_id": chosen["run_id"],
        "prompt": shared_prompt,
        "chosen": {
            "branch_id": chosen["branch_id"],
            "request_ids": chosen["request_ids"],
            "status": chosen["status"],
            "prompt": chosen["prompt"],
            "trajectory": chosen["trajectory"],
            "terminal_output": chosen["terminal_output"],
        },
        "rejected": {
            "branch_id": rejected["branch_id"],
            "request_ids": rejected["request_ids"],
            "status": rejected["status"],
            "prompt": rejected["prompt"],
            "trajectory": rejected["trajectory"],
            "terminal_output": rejected["terminal_output"],
        },
        "source": source,
        "supervision": {
            "type": "preference",
            "source": source,
            "reason": reason,
            "confidence": artifact.confidence if artifact is not None else None,
        },
        "lineage": {
            "builder": "preference",
            "artifact_id": artifact.artifact_id if artifact is not None else None,
            "target_ref": artifact.target_ref if artifact is not None else None,
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


def _artifact_in_scope(
    *,
    artifact: ArtifactRecord,
    run_ids: set[str],
    session_ids: set[str],
    fact_ids: set[str],
    branch_ids: set[str],
) -> bool:
    if artifact.run_id is not None and artifact.run_id in run_ids:
        return True
    target_type, target_id = _split_target_ref(artifact.target_ref)
    if target_type == "run":
        return target_id in run_ids
    if target_type == "session":
        return target_id in session_ids
    if target_type == "fact":
        return target_id in fact_ids
    if target_type == "branch":
        return target_id in branch_ids or (
            artifact.run_id is not None and artifact.run_id in run_ids
        )
    if target_type is None and artifact.session_id is not None:
        return artifact.session_id in session_ids
    return False


def _manifest_path(out: Path) -> Path:
    return out.with_name(f"{out.name}.manifest.json")


def _single_session_id(facts: list[FactEvent]) -> str | None:
    session_ids = sorted({fact.session_id for fact in facts})
    return session_ids[0] if len(session_ids) == 1 else None


def _run_session_map(facts: list[FactEvent]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for fact in facts:
        mapping.setdefault(fact.run_id, fact.session_id)
    return mapping


def _record_run_id(record: dict[str, Any]) -> str | None:
    value = record.get("run_id")
    if isinstance(value, str) and value:
        return value
    target = record.get("target")
    if isinstance(target, dict):
        target_run_id = target.get("run_id")
        if isinstance(target_run_id, str) and target_run_id:
            return target_run_id
    return None


def _scope_contract_blockers(
    *,
    builder: str,
    cohort: CohortRecord | None,
    cohort_members: list[CohortMemberRecord] | None,
    legacy_scope: bool,
) -> list[str]:
    del cohort_members, legacy_scope
    if cohort is None:
        return []

    blockers: list[str] = []
    review = cohort.manifest.get("review")
    if isinstance(review, dict) and review.get("required") is True:
        blockers.append("cohort has pending review queue items")

    expected_use = str(cohort.manifest.get("expected_use") or "training")
    if builder != "facts" and expected_use != "training":
        blockers.append(
            f"cohort expected_use={expected_use} is not exportable as a training dataset snapshot"
        )

    cohort_sample_unit = cohort.manifest.get("sample_unit")
    if isinstance(cohort_sample_unit, str) and cohort_sample_unit:
        builder_sample_unit = _sample_unit_for_builder(builder)
        if not _builder_sample_unit_is_compatible(
            builder=builder,
            builder_sample_unit=builder_sample_unit,
            cohort_sample_unit=cohort_sample_unit,
        ):
            blockers.append(
                "builder sample_unit is incompatible with cohort slice contract: "
                f"builder={builder_sample_unit}, cohort={cohort_sample_unit}"
            )
    return blockers


def _builder_sample_unit_is_compatible(
    *,
    builder: str,
    builder_sample_unit: str,
    cohort_sample_unit: str,
) -> bool:
    if builder == "facts":
        return True
    compatibility = {
        "sft": {"request", "run"},
        "preference": {"branch"},
        "binary_rl": {"run"},
    }
    allowed = compatibility.get(builder, {builder_sample_unit})
    return cohort_sample_unit in allowed


def _facts_time_range(facts: list[FactEvent]) -> dict[str, str | None]:
    if not facts:
        return {"start": None, "end": None}
    ordered = sorted(fact.timestamp.isoformat() for fact in facts)
    return {"start": ordered[0], "end": ordered[-1]}


def _unique_annotation_values(records: list[dict[str, Any]], key: str) -> list[str]:
    values = {
        value
        for record in records
        for value in [
            record.get(key),
            record.get("annotation", {}).get(key)
            if isinstance(record.get("annotation"), dict)
            else None,
        ]
        if isinstance(value, str) and value
    }
    return sorted(values)


def _request_input_messages(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    request_json = payload.get("json")
    if isinstance(request_json, dict):
        return extract_prompt_messages(request_json)
    input_messages = payload.get("input_messages")
    if isinstance(input_messages, list):
        return [item for item in input_messages if isinstance(item, dict)] or None
    return None


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
    cohort_id: str | None,
    dataset_recipe_id: str,
    dataset_snapshot_id: str,
    sample_unit: str,
    split_manifest: dict[str, Any],
    dedupe_manifest: dict[str, Any],
    records: list[dict[str, Any]],
    cohort: CohortRecord | None,
    legacy_scope: bool,
) -> dict[str, Any]:
    annotation_summary = summarize_e1_annotations(facts=facts, artifacts=artifacts)
    split_guard_keys = sorted(
        {
            value
            for record in records
            for value in [record.get("split_guard_key")]
            if isinstance(value, str) and value
        }
    )
    leakage_guard = {
        "primary": "task_instance_key",
        "fallbacks": ["run_id", "session_id", "request_id", "fact_id"],
        "fallback_used": any(
            not guard_key.startswith("task_instance_key:")
            for guard_key in split_guard_keys
        ),
        "guard_keys": split_guard_keys,
    }
    scope_mode = "legacy_preview" if legacy_scope else "cohort"
    return {
        "dataset_snapshot_id": dataset_snapshot_id,
        "dataset_recipe_id": dataset_recipe_id,
        "builder": builder,
        "sample_unit": sample_unit,
        "created_at": datetime.now(UTC).isoformat(),
        "cohort_id": cohort_id,
        "session_id": session_id,
        "run_id": run_id,
        "scope": {
            "mode": scope_mode,
            "legacy_preview": legacy_scope,
            "cohort_id": cohort_id,
        },
        "record_count": record_count,
        "ready": not blockers and record_count > 0,
        "blockers": blockers,
        "output_path": str(output_path) if output_path is not None else None,
        "source_run_ids": sorted({fact.run_id for fact in facts}),
        "source_session_ids": sorted({fact.session_id for fact in facts}),
        "task_instance_keys": _unique_annotation_values(records, "task_instance_key"),
        "task_template_hashes": _unique_annotation_values(records, "task_template_hash"),
        "taxonomy_versions": _unique_annotation_values(records, "taxonomy_version"),
        "time_range": _facts_time_range(facts),
        "fact_count": len(facts),
        "artifact_count": len(artifacts),
        "artifact_ids": [artifact.artifact_id for artifact in artifacts],
        "split": {
            **split_manifest,
            "guard_key_priority": [
                "task_instance_key",
                "run_id",
                "session_id",
                "request_id",
                "fact_id",
            ],
            "leakage_guard": leakage_guard,
        },
        "dedupe": dedupe_manifest,
        "distributions": {
            "task_family": _distribution_from_records(records, "task_family"),
            "task_type": _distribution_from_records(records, "task_type"),
            "task_template_hash": _distribution_from_records(records, "task_template_hash"),
            "difficulty": _distribution_from_records(records, "difficulty"),
            "teacher_model": _distribution_from_records(records, "teacher_model"),
            "verifier_name": _distribution_from_records(records, "verifier_name"),
            "source_channel": _distribution_from_records(records, "source_channel"),
            "split": _distribution_from_records(records, "split"),
        },
        "artifact_view": (
            cohort.manifest.get("artifact_view")
            if cohort is not None and isinstance(cohort.manifest.get("artifact_view"), dict)
            else {
                "strategy": "latest_only"
                if legacy_scope
                else "historical_replay_before_cohort_created_at"
            }
        ),
        "cohort_contract": (
            {
                "expected_use": cohort.manifest.get("expected_use"),
                "review": cohort.manifest.get("review"),
                "quality_gate": cohort.manifest.get("quality", {}).get("quality_gate"),
                "selection_query": cohort.manifest.get("selection_query"),
            }
            if cohort is not None
            else None
        ),
        "evidence": {
            "level": annotation_summary["level"],
            "ready": annotation_summary["ready"],
            "annotation_artifacts": annotation_summary["annotation_artifacts"],
            "annotated_runs": annotation_summary["annotated_runs"],
            "run_count": annotation_summary["run_count"],
            "required_fields": annotation_summary["required_fields"],
            "artifact_ids": annotation_summary["artifact_ids"],
            "runs": annotation_summary["runs"],
        },
    }


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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, dict):
        for key in ("text", "content", "value", "output"):
            nested = _normalize_content(value.get(key))
            if nested is not None:
                return nested
        if value:
            return json.dumps(value, ensure_ascii=True, sort_keys=True)
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
                    or item.get("output")
                )
            elif isinstance(item, str):
                text = item
            if text:
                parts.append(text)
        if parts:
            return "\n".join(parts)
        if value:
            return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return None


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


_ensure_builtin_builders_registered()
