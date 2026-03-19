"""Replay rendering helpers."""

from __future__ import annotations

import json

from clawgraph.graph.correlation import correlate_request_groups, infer_branches
from clawgraph.protocol.models import ArtifactRecord, FactEvent


def _summarize_payload(fact: FactEvent) -> str:
    payload = fact.payload

    if "path" in payload and "status_code" in payload:
        return f'{payload["path"]} status={payload["status_code"]}'
    if "path" in payload:
        return str(payload["path"])
    if "error" in payload:
        return str(payload["error"])
    if "content_type" in payload:
        return str(payload["content_type"])

    compact = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    if len(compact) > 96:
        compact = compact[:93] + "..."
    return compact


def render_session_replay(
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord] | None = None,
) -> str:
    """Render a session replay as simple text."""

    if not facts:
        return "No facts found."

    lines = [
        f"Session: {facts[0].session_id}",
        f"Run: {facts[0].run_id}",
        f"Facts: {len(facts)}",
        "",
    ]

    for fact in facts:
        timestamp = fact.timestamp.isoformat(timespec="seconds")
        summary = _summarize_payload(fact)
        lines.append(f"{timestamp}  {fact.actor:7}  {fact.kind:18}  {summary}")

    groups = correlate_request_groups(facts)
    if groups:
        branches, request_branch_map = infer_branches(groups, facts=facts)
        lines.extend(["", "Request groups:"])
        for index, group in enumerate(groups, start=1):
            branch_id = request_branch_map.get(group.request.fact_id, "br_main")
            status = group.outcome
            request_id = group.request.request_id or group.request.fact_id
            lines.append(
                f"{index:02d}. {group.actor} {group.path} "
                f"status={status} chunks={len(group.response_chunks)} "
                f"request={request_id} branch={branch_id}"
            )

        if branches:
            lines.extend(["", "Inferred branches:"])
            for branch in branches:
                reason = f" reason={branch.open_reason}" if branch.open_reason else ""
                parent = (
                    f" parent={branch.parent_branch_id}"
                    if branch.parent_branch_id is not None
                    else ""
                )
                lines.append(
                    f"{branch.branch_id} type={branch.branch_type} "
                    f"source={branch.source} status={branch.status}{parent}{reason}"
                )

    if artifacts:
        lines.extend(["", f"Artifacts: {len(artifacts)}"])
        for artifact in artifacts:
            lines.append(
                f"{artifact.artifact_id} {artifact.artifact_type} "
                f"target={artifact.target_ref} producer={artifact.producer} "
                f"status={artifact.status}"
            )

    return "\n".join(lines)
