"""Correlation and branch inference helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from clawgraph.protocol.models import BranchRecord, FactEvent


@dataclass(slots=True)
class CorrelatedRequestGroup:
    """A request plus its derived response lifecycle."""

    request: FactEvent
    response_chunks: list[FactEvent] = field(default_factory=list)
    response: FactEvent | None = None
    error: FactEvent | None = None

    @property
    def actor(self) -> str:
        return self.request.actor

    @property
    def path(self) -> str:
        value = self.request.payload.get("path")
        return str(value) if value is not None else "<unknown>"

    @property
    def status_code(self) -> int | None:
        if self.response is not None:
            value = self.response.payload.get("status_code")
            if isinstance(value, int):
                return value
        if self.error is not None:
            value = self.error.payload.get("status_code")
            if isinstance(value, int):
                return value
        return None

    @property
    def outcome(self) -> str:
        status_code = self.status_code
        if self.error is not None:
            return "failed"
        if status_code is not None and status_code >= 400:
            return "failed"
        if self.response is not None:
            return "succeeded"
        return "open"

    @property
    def hinted_branch_type(self) -> str | None:
        headers = self.request.payload.get("headers")
        if not isinstance(headers, dict):
            return None
        value = headers.get("x-clawgraph-branch-type")
        if isinstance(value, str) and value:
            return value
        return None

    @property
    def hinted_parent_request_id(self) -> str | None:
        headers = self.request.payload.get("headers")
        if not isinstance(headers, dict):
            return None
        value = headers.get("x-clawgraph-parent-id")
        if isinstance(value, str) and value:
            return value
        return None


def correlate_request_groups(facts: list[FactEvent]) -> list[CorrelatedRequestGroup]:
    """Correlate requests with response chunks, final responses, and errors."""

    groups: dict[str, CorrelatedRequestGroup] = {}
    ordered_request_ids: list[str] = []

    for fact in facts:
        if fact.kind == "request_started":
            groups[fact.fact_id] = CorrelatedRequestGroup(request=fact)
            ordered_request_ids.append(fact.fact_id)

    for fact in facts:
        parent_ref = fact.parent_ref
        if parent_ref is None or parent_ref not in groups:
            continue

        group = groups[parent_ref]
        if fact.kind == "response_chunk":
            group.response_chunks.append(fact)
        elif fact.kind == "response_finished":
            group.response = fact
        elif fact.kind == "error_raised":
            group.error = fact

    return [groups[fact_id] for fact_id in ordered_request_ids]


def infer_branches(
    groups: list[CorrelatedRequestGroup],
    *,
    facts: list[FactEvent] | None = None,
) -> tuple[list[BranchRecord], dict[str, str]]:
    """Infer a basic branch structure from correlated request groups."""

    if not groups:
        return [], {}

    declared_open_hints, declared_close_hints = _collect_declared_branch_hints(facts or [])
    branches: list[BranchRecord] = [
        BranchRecord(
            branch_id="br_main",
            schema_version="v1",
            run_id=groups[0].request.run_id,
            branch_type="mainline",
            status="open",
            source="inferred",
            opened_at_fact_id=groups[0].request.fact_id,
            metadata={"inferred": True},
        )
    ]
    request_branch_map: dict[str, str] = {}
    request_to_branch: dict[str, str] = {}
    request_id_to_branch: dict[str, str] = {}
    previous_by_signature: dict[tuple[str, str], CorrelatedRequestGroup] = {}
    branch_counter = 0

    for index, group in enumerate(groups):
        branch_id = "br_main"
        parent_branch_id = "br_main"
        branch_type = group.hinted_branch_type
        branch_source = "inferred"
        opened_at_fact_id = group.request.fact_id
        closed_at_fact_id = _closing_fact_id(group)
        open_reason: str | None = None

        hinted_parent_request_id = group.hinted_parent_request_id
        declared_hint = _match_declared_branch_hint(
            group.request,
            declared_open_hints,
        )
        if declared_hint is not None:
            branch_type = declared_hint["branch_type"]
            branch_source = "declared"
            open_reason = f"semantic:{declared_hint['semantic_kind']}"
            parent_branch_id = _resolve_parent_branch_id(
                declared_hint=declared_hint,
                request_to_branch=request_to_branch,
                request_id_to_branch=request_id_to_branch,
            )
            branch_counter += 1
            branch_id = declared_hint["branch_id"] or f"br_{branch_type}_{branch_counter}"
            status = declared_hint["status"] or (
                "succeeded" if group.outcome == "succeeded" else "failed"
            )
            close_hint = _match_declared_close_hint(branch_id, group.request, declared_close_hints)
            if close_hint is not None:
                status = close_hint["status"] or status
                closed_at_fact_id = close_hint["fact_id"]
            branches.append(
                BranchRecord(
                    branch_id=branch_id,
                    schema_version="v1",
                    run_id=group.request.run_id,
                    branch_type=branch_type,
                    status=status,
                    source=branch_source,
                    parent_branch_id=parent_branch_id,
                    opened_at_fact_id=opened_at_fact_id,
                    closed_at_fact_id=closed_at_fact_id,
                    open_reason=open_reason,
                    metadata={
                        "declared": True,
                        "request_fact_id": group.request.fact_id,
                        "semantic_fact_id": declared_hint["semantic_fact_id"],
                    },
                )
            )
        elif branch_type is not None:
            parent_branch_id = request_to_branch.get(hinted_parent_request_id or "", "br_main")
            branch_counter += 1
            branch_id = f"br_{branch_type}_{branch_counter}"
            branches.append(
                BranchRecord(
                    branch_id=branch_id,
                    schema_version="v1",
                    run_id=group.request.run_id,
                    branch_type=branch_type,
                    status="succeeded" if group.outcome == "succeeded" else "failed",
                    source="inferred",
                    parent_branch_id=parent_branch_id,
                    opened_at_fact_id=opened_at_fact_id,
                    closed_at_fact_id=closed_at_fact_id,
                    open_reason="hinted_branch_type",
                    metadata={"inferred": True, "request_fact_id": group.request.fact_id},
                )
            )
        elif hinted_parent_request_id is not None:
            parent_branch_id = request_to_branch.get(hinted_parent_request_id, "br_main")
            branch_counter += 1
            branch_id = f"br_subagent_{branch_counter}"
            branches.append(
                BranchRecord(
                    branch_id=branch_id,
                    schema_version="v1",
                    run_id=group.request.run_id,
                    branch_type="subagent",
                    status="succeeded" if group.outcome == "succeeded" else "failed",
                    source="inferred",
                    parent_branch_id=parent_branch_id,
                    opened_at_fact_id=opened_at_fact_id,
                    closed_at_fact_id=closed_at_fact_id,
                    open_reason=f"parent_request:{hinted_parent_request_id}",
                    metadata={"inferred": True, "request_fact_id": group.request.fact_id},
                )
            )
        else:
            signature = (group.actor, group.path)
            previous = previous_by_signature.get(signature)
            if previous is not None and previous.outcome == "failed":
                branch_counter += 1
                branch_id = f"br_retry_{branch_counter}"
                parent_branch_id = request_to_branch.get(previous.request.fact_id, "br_main")
                branches.append(
                    BranchRecord(
                        branch_id=branch_id,
                        schema_version="v1",
                        run_id=group.request.run_id,
                        branch_type="retry",
                        status="succeeded" if group.outcome == "succeeded" else "failed",
                        source="inferred",
                        parent_branch_id=parent_branch_id,
                        opened_at_fact_id=opened_at_fact_id,
                        closed_at_fact_id=closed_at_fact_id,
                        open_reason=f"retry_after:{previous.request.fact_id}",
                        metadata={"inferred": True, "request_fact_id": group.request.fact_id},
                    )
                )

            previous_by_signature[signature] = group

        request_to_branch[group.request.fact_id] = branch_id
        request_branch_map[group.request.fact_id] = branch_id
        if group.request.request_id:
            request_id_to_branch[group.request.request_id] = branch_id

    mainline_status = "open"
    if all(group.outcome == "succeeded" for group in groups):
        mainline_status = "succeeded"
    elif any(group.outcome == "failed" for group in groups):
        mainline_status = "failed"
    branches[0].status = mainline_status
    branches[0].closed_at_fact_id = _closing_fact_id(groups[-1])
    return branches, request_branch_map


def _closing_fact_id(group: CorrelatedRequestGroup) -> str | None:
    if group.response is not None:
        return group.response.fact_id
    if group.error is not None:
        return group.error.fact_id
    return None


def _collect_declared_branch_hints(
    facts: list[FactEvent],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    open_hints: list[dict[str, Any]] = []
    close_hints: list[dict[str, Any]] = []
    for fact in facts:
        if fact.kind != "semantic_event":
            continue
        semantic_kind = _semantic_kind(fact)
        if semantic_kind is None:
            continue
        semantic_payload = _semantic_payload(fact)
        fact_ref = _semantic_fact_ref(fact)
        target_request_fact_id = _string_value(semantic_payload.get("request_fact_id"))
        if target_request_fact_id is None and fact_ref is not None and fact_ref.startswith("fact_"):
            target_request_fact_id = fact_ref
        hint = {
            "semantic_fact_id": fact.fact_id,
            "semantic_kind": semantic_kind,
            "fact_id": fact.fact_id,
            "branch_id": _string_value(semantic_payload.get("branch_id")),
            "branch_type": _string_value(semantic_payload.get("branch_type"))
            or _branch_type_from_semantic_kind(semantic_kind),
            "status": _string_value(semantic_payload.get("status")),
            "target_request_fact_id": target_request_fact_id,
            "target_request_id": _string_value(semantic_payload.get("request_id")),
            "parent_request_fact_id": _string_value(
                semantic_payload.get("parent_request_fact_id")
            ),
            "parent_request_id": _string_value(semantic_payload.get("parent_request_id")),
            "parent_branch_id": _string_value(semantic_payload.get("parent_branch_id")),
        }
        if semantic_kind == "branch_close_declared":
            close_hints.append(hint)
            continue
        if hint["target_request_fact_id"] is None and hint["target_request_id"] is None:
            continue
        if hint["branch_type"] is None:
            continue
        open_hints.append(hint)
    return open_hints, close_hints


def _match_declared_branch_hint(
    request_fact: FactEvent,
    hints: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for hint in hints:
        if hint["target_request_fact_id"] == request_fact.fact_id:
            return hint
        if request_fact.request_id and hint["target_request_id"] == request_fact.request_id:
            return hint
    return None


def _match_declared_close_hint(
    branch_id: str,
    request_fact: FactEvent,
    hints: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for hint in hints:
        if hint["branch_id"] and hint["branch_id"] == branch_id:
            return hint
        if hint["target_request_fact_id"] == request_fact.fact_id:
            return hint
        if request_fact.request_id and hint["target_request_id"] == request_fact.request_id:
            return hint
    return None


def _resolve_parent_branch_id(
    *,
    declared_hint: dict[str, Any],
    request_to_branch: dict[str, str],
    request_id_to_branch: dict[str, str],
) -> str:
    explicit_parent_branch_id = declared_hint["parent_branch_id"]
    if explicit_parent_branch_id is not None:
        return explicit_parent_branch_id
    parent_request_fact_id = declared_hint["parent_request_fact_id"]
    if parent_request_fact_id is not None:
        return request_to_branch.get(parent_request_fact_id, "br_main")
    parent_request_id = declared_hint["parent_request_id"]
    if parent_request_id is not None:
        return request_id_to_branch.get(parent_request_id, "br_main")
    return "br_main"


def _semantic_kind(fact: FactEvent) -> str | None:
    value = fact.payload.get("semantic_kind") or fact.payload.get("kind")
    return _string_value(value)


def _semantic_fact_ref(fact: FactEvent) -> str | None:
    return _string_value(fact.payload.get("fact_ref"))


def _semantic_payload(fact: FactEvent) -> dict[str, Any]:
    payload = fact.payload.get("payload")
    if isinstance(payload, dict):
        return payload
    return {}


def _branch_type_from_semantic_kind(semantic_kind: str) -> str | None:
    mapping = {
        "retry_declared": "retry",
        "fallback_declared": "fallback",
        "branch_open_declared": None,
        "subagent_spawned": "subagent",
    }
    return mapping.get(semantic_kind)


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
