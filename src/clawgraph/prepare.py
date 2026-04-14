"""Generic trajectory preparation and cleaning helpers for phase-2 workflows."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from clawgraph.graph import build_branch_inspect_summaries, build_request_span_summaries
from clawgraph.protocol.factories import new_artifact_record
from clawgraph.protocol.models import ArtifactRecord, FactEvent
from clawgraph.protocol.semantics import extract_prompt_messages
from clawgraph.redaction import redact_secret_like_text, summarize_secret_like_matches

PREPARE_ANNOTATION_KIND = "trajectory_prepare"
DEFAULT_PREPARE_VERSION = "clawgraph.prepare.v1"
PREPARE_ARTIFACT_TYPE = "workflow_report"


@dataclass(slots=True)
class PrepareRunPlan:
    """Planned run-level preparation artifact."""

    session_id: str
    run_id: str
    producer: str
    summary: dict[str, Any]
    blocker_reasons: list[str]
    review_reasons: list[str]
    artifact: ArtifactRecord

    def to_dict(self) -> dict[str, Any]:
        artifact_dict = asdict(self.artifact)
        artifact_dict["created_at"] = (
            self.artifact.created_at.isoformat() if self.artifact.created_at is not None else None
        )
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "producer": self.producer,
            "summary": self.summary,
            "blocker_reasons": list(self.blocker_reasons),
            "review_reasons": list(self.review_reasons),
            "artifact": artifact_dict,
        }


def plan_prepare_run_artifact(
    *,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
    producer: str,
    version: str | None = None,
    status: str = "active",
) -> PrepareRunPlan:
    """Plan one run-level preparation artifact without mutating facts."""

    if not facts:
        raise ValueError("no facts found")
    run_ids = sorted({fact.run_id for fact in facts})
    if len(run_ids) != 1:
        raise ValueError("prepare expects a single-run fact scope")
    session_ids = sorted({fact.session_id for fact in facts})
    if len(session_ids) != 1:
        raise ValueError("prepare expects a single-session fact scope")

    session_id = session_ids[0]
    run_id = run_ids[0]
    summary = _build_prepare_summary(facts=facts, artifacts=artifacts)
    blocker_reasons: list[str] = []
    review_reasons: list[str] = []
    if summary["request_count"] == 0:
        blocker_reasons.append("missing_request_spans")
    if summary["open_count"] > 0:
        blocker_reasons.append("open_request_spans")
    if summary["prompt_request_count"] == 0:
        blocker_reasons.append("missing_prompt_messages")
    if summary["secret_match_count"] > 0:
        review_reasons.append("secret_like_content_detected")
    if summary["declared_branch_ratio"] == 0.0 and summary["branch_count"] > 1:
        review_reasons.append("inferred_only_branching")
    if summary["assistant_response_count"] == 0 and summary["success_count"] > 0:
        review_reasons.append("missing_assistant_output")

    prepare_status = (
        "blocked"
        if blocker_reasons
        else "review"
        if review_reasons
        else "clean"
    )
    payload = {
        "annotation_kind": PREPARE_ANNOTATION_KIND,
        "prepare_version": version or DEFAULT_PREPARE_VERSION,
        "prepare_status": prepare_status,
        "blocker_reasons": list(dict.fromkeys(blocker_reasons)),
        "review_reasons": list(dict.fromkeys(review_reasons)),
        **summary,
    }
    artifact = new_artifact_record(
        artifact_type=PREPARE_ARTIFACT_TYPE,
        target_ref=f"run:{run_id}",
        producer=producer,
        payload=payload,
        version=version,
        session_id=session_id,
        run_id=run_id,
        status=status,
        confidence=1.0 if prepare_status == "clean" else 0.7 if prepare_status == "review" else 0.4,
        metadata={
            "prepare_status": prepare_status,
            "secret_match_count": summary["secret_match_count"],
            "prompt_request_count": summary["prompt_request_count"],
            "assistant_response_count": summary["assistant_response_count"],
        },
    )
    return PrepareRunPlan(
        session_id=session_id,
        run_id=run_id,
        producer=producer,
        summary=summary,
        blocker_reasons=list(dict.fromkeys(blocker_reasons)),
        review_reasons=list(dict.fromkeys(review_reasons)),
        artifact=artifact,
    )


def resolve_prepare_annotation_for_run(
    *,
    session_id: str,
    run_id: str,
    artifacts: list[ArtifactRecord],
) -> tuple[dict[str, Any], list[str]]:
    """Return the latest active prepare payload for one run."""

    candidates = [
        artifact
        for artifact in artifacts
        if artifact.status == "active"
        and artifact.artifact_type == PREPARE_ARTIFACT_TYPE
        and artifact.payload.get("annotation_kind") == PREPARE_ANNOTATION_KIND
        and artifact.session_id == session_id
        and artifact.run_id == run_id
    ]
    if not candidates:
        return {}, []
    selected = max(
        candidates,
        key=lambda artifact: (
            artifact.created_at.isoformat() if artifact.created_at is not None else "",
            artifact.artifact_id,
        ),
    )
    return dict(selected.payload), [selected.artifact_id]


def get_prepare_artifact_for_run(
    *,
    session_id: str,
    run_id: str,
    artifacts: list[ArtifactRecord],
) -> ArtifactRecord | None:
    """Return the latest active prepare artifact for one run."""

    candidates = [
        artifact
        for artifact in artifacts
        if artifact.status == "active"
        and artifact.artifact_type == PREPARE_ARTIFACT_TYPE
        and artifact.payload.get("annotation_kind") == PREPARE_ANNOTATION_KIND
        and artifact.session_id == session_id
        and artifact.run_id == run_id
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda artifact: (
            artifact.created_at.isoformat() if artifact.created_at is not None else "",
            artifact.artifact_id,
        ),
    )


def _build_prepare_summary(
    *,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
) -> dict[str, Any]:
    request_summaries = build_request_span_summaries(facts, artifacts)
    branch_summaries = build_branch_inspect_summaries(facts, artifacts)
    prompt_texts: list[str] = []
    response_texts: list[str] = []
    prompt_request_count = 0
    assistant_response_count = 0
    for fact in facts:
        if fact.kind == "request_started":
            prompt_text = _prompt_text_from_request_fact(fact, redact=False)
            if prompt_text:
                prompt_request_count += 1
                prompt_texts.append(prompt_text)
        elif fact.kind == "response_finished":
            response_text = _assistant_text_from_response_fact(fact, redact=False)
            if response_text:
                assistant_response_count += 1
                response_texts.append(response_text)

    secret_matches = summarize_secret_like_matches([*prompt_texts, *response_texts])
    declared_branch_count = sum(1 for branch in branch_summaries if branch.source == "declared")
    return {
        "request_count": len(request_summaries),
        "success_count": sum(1 for summary in request_summaries if summary.outcome == "succeeded"),
        "failure_count": sum(1 for summary in request_summaries if summary.outcome == "failed"),
        "open_count": sum(1 for summary in request_summaries if summary.outcome == "open"),
        "branch_count": len(branch_summaries),
        "declared_branch_count": declared_branch_count,
        "declared_branch_ratio": (
            round(declared_branch_count / len(branch_summaries), 4)
            if branch_summaries
            else 1.0
        ),
        "prompt_request_count": prompt_request_count,
        "assistant_response_count": assistant_response_count,
        "secret_matches": secret_matches,
        "secret_match_count": sum(secret_matches.values()),
        "request_samples": [_fact_preview(fact) for fact in facts if fact.kind == "request_started"][:3],
        "response_samples": [_fact_preview(fact) for fact in facts if fact.kind == "response_finished"][:3],
    }


def _prompt_text_from_request_fact(fact: FactEvent, *, redact: bool) -> str | None:
    payload_json = fact.payload.get("json")
    if not isinstance(payload_json, dict):
        preview = fact.payload.get("preview")
        if not isinstance(preview, str) or not preview:
            return None
        return redact_secret_like_text(preview) if redact else preview
    messages = extract_prompt_messages(payload_json)
    if not messages:
        return None
    parts: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str) and content:
            parts.append(content)
    if not parts:
        return None
    text = "\n".join(parts)
    return redact_secret_like_text(text) if redact else text


def _assistant_text_from_response_fact(fact: FactEvent, *, redact: bool) -> str | None:
    canonical = fact.payload.get("canonical")
    if isinstance(canonical, dict):
        assistant_message = canonical.get("assistant_message")
        if isinstance(assistant_message, dict):
            content = assistant_message.get("content")
            if isinstance(content, str) and content:
                return redact_secret_like_text(content) if redact else content
    payload_json = fact.payload.get("json")
    if isinstance(payload_json, dict):
        choices = payload_json.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content:
                        return redact_secret_like_text(content) if redact else content
        output = payload_json.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    texts = [
                        entry.get("text")
                        for entry in content
                        if isinstance(entry, dict) and isinstance(entry.get("text"), str)
                    ]
                    if texts:
                        text = "\n".join(texts)
                        return redact_secret_like_text(text) if redact else text
    preview = fact.payload.get("preview")
    if isinstance(preview, str) and preview:
        return redact_secret_like_text(preview) if redact else preview
    text = fact.payload.get("text")
    if isinstance(text, str) and text:
        return redact_secret_like_text(text) if redact else text
    return None


def _fact_preview(fact: FactEvent) -> str | None:
    if fact.kind == "request_started":
        return _prompt_text_from_request_fact(fact, redact=True)
    if fact.kind == "response_finished":
        return _assistant_text_from_response_fact(fact, redact=True)
    preview = fact.payload.get("preview")
    if isinstance(preview, str) and preview:
        return redact_secret_like_text(preview)
    payload_json = fact.payload.get("json")
    if isinstance(payload_json, dict):
        return redact_secret_like_text(json.dumps(payload_json, ensure_ascii=True, sort_keys=True)[:200])
    return None
