"""Replay rendering helpers."""

from __future__ import annotations

import json

from clawgraph.graph.correlation import correlate_request_groups, infer_branches, partition_facts_by_run
from clawgraph.graph.overlays import (
    branch_artifact_overlays,
    request_artifact_overlays,
    run_artifact_overlays,
    session_artifact_overlays,
)
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

    run_partitions = partition_facts_by_run(facts)
    if len(run_partitions) > 1:
        lines = [
            f"Session: {facts[0].session_id}",
            f"Runs: {len(run_partitions)}",
            f"Facts: {len(facts)}",
        ]
        session_artifacts = session_artifact_overlays(
            session_id=facts[0].session_id,
            artifacts=artifacts,
        )
        for run_id, run_facts in run_partitions:
            run_artifacts = [
                artifact
                for artifact in artifacts or []
                if artifact.run_id == run_id
            ]
            lines.extend(
                [
                    "",
                    f"Run: {run_id}",
                    _render_run_replay(run_facts, run_artifacts).strip(),
                ]
            )
        if session_artifacts:
            lines.extend(["", f"Session-scoped artifacts: {len(session_artifacts)}"])
            for artifact in session_artifacts:
                lines.append(
                    f"{artifact.artifact_id} {artifact.artifact_type} "
                    f"target={artifact.target_ref} producer={artifact.producer} "
                    f"status={artifact.status}"
                )
        return "\n".join(lines)

    run_id, run_facts = run_partitions[0]
    run_artifacts = [
        artifact for artifact in artifacts or [] if artifact.run_id in {None, run_id}
    ]
    return _render_run_replay(run_facts, run_artifacts)


def _render_run_replay(
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord] | None = None,
) -> str:
    """Render replay lines for a single run."""

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
            request_overlays = request_artifact_overlays(group, artifacts)
            lines.append(
                f"{index:02d}. {group.actor} {group.path} "
                f"status={status} chunks={len(group.response_chunks)} "
                f"request={request_id} branch={branch_id} "
                f"artifacts={len(request_overlays)}"
            )
            for artifact in request_overlays:
                lines.append(
                    f"    overlay {artifact.artifact_type} "
                    f"target={artifact.target_ref} producer={artifact.producer}"
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
                branch_overlays = branch_artifact_overlays(
                    branch_id=branch.branch_id,
                    run_id=branch.run_id,
                    artifacts=artifacts,
                )
                lines.append(
                    f"{branch.branch_id} type={branch.branch_type} "
                    f"source={branch.source} status={branch.status}{parent}{reason} "
                    f"artifacts={len(branch_overlays)}"
                )
                for artifact in branch_overlays:
                    lines.append(
                        f"    overlay {artifact.artifact_type} "
                        f"target={artifact.target_ref} producer={artifact.producer}"
                    )

    if artifacts:
        run_overlays = run_artifact_overlays(run_id=facts[0].run_id, artifacts=artifacts)
        session_overlays = session_artifact_overlays(
            session_id=facts[0].session_id,
            artifacts=artifacts,
        )
        lines.extend(["", f"Artifacts: {len(artifacts)}"])
        if run_overlays:
            lines.append(f"Run-scoped artifacts: {len(run_overlays)}")
        if session_overlays:
            lines.append(f"Session-scoped artifacts: {len(session_overlays)}")
        for artifact in artifacts:
            lines.append(
                f"{artifact.artifact_id} {artifact.artifact_type} "
                f"target={artifact.target_ref} producer={artifact.producer} "
                f"status={artifact.status}"
            )

    return "\n".join(lines)
