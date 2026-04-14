"""Generic run-level judge helpers for phase-2 annotation workflows."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

from clawgraph.artifacts import (
    E1_ANNOTATION_KIND,
    E1_REQUIRED_FIELDS,
    build_e1_annotation_artifacts,
    resolve_e1_annotation_for_run,
)
from clawgraph.graph import build_branch_inspect_summaries, build_request_span_summaries
from clawgraph.protocol.factories import new_artifact_record
from clawgraph.protocol.models import ArtifactRecord, FactEvent
from clawgraph.protocol.semantics import extract_prompt_messages
from clawgraph.redaction import redact_secret_like_text


DEFAULT_JUDGE_PROVIDER = "heuristic"
DEFAULT_TAXONOMY_VERSION = "judge.taxonomy.v1"
DEFAULT_ANNOTATION_VERSION = "judge.e1.v1"


@dataclass(slots=True)
class JudgeAnnotationPlan:
    """Planned E1 annotation produced by a pluggable judge."""

    provider: str
    model: str | None
    session_id: str
    run_id: str
    warnings: list[str]
    review_reasons: list[str]
    run_summary: dict[str, Any]
    parsed_response: dict[str, Any] | None
    raw_response: str | None
    artifact: ArtifactRecord

    def to_dict(self) -> dict[str, Any]:
        artifact_dict = asdict(self.artifact)
        artifact_dict["created_at"] = (
            self.artifact.created_at.isoformat() if self.artifact.created_at is not None else None
        )
        return {
            "provider": self.provider,
            "model": self.model,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "warnings": list(self.warnings),
            "review_reasons": list(self.review_reasons),
            "run_summary": self.run_summary,
            "parsed_response": self.parsed_response,
            "raw_response": self.raw_response,
            "artifact": artifact_dict,
        }


def plan_judge_annotation(
    *,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
    producer: str,
    provider: str = DEFAULT_JUDGE_PROVIDER,
    version: str | None = None,
    status: str = "active",
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
    instructions: str | None = None,
    task_family: str | None = None,
    task_type: str | None = None,
    taxonomy_version: str | None = None,
    annotation_version: str | None = None,
    source_channel: str | None = None,
    task_instance_key: str | None = None,
    supersedes_artifact_id: str | None = None,
    timeout_seconds: float = 60.0,
) -> JudgeAnnotationPlan:
    """Plan one versioned E1 annotation artifact for a single run."""

    if not facts:
        raise ValueError("no facts found")

    run_ids = sorted({fact.run_id for fact in facts})
    if len(run_ids) != 1:
        raise ValueError("judge annotation expects a single-run fact scope")
    session_ids = sorted({fact.session_id for fact in facts})
    if len(session_ids) != 1:
        raise ValueError("judge annotation expects a single-session fact scope")

    session_id = session_ids[0]
    run_id = run_ids[0]
    bootstrap = build_e1_annotation_artifacts(
        facts=facts,
        producer=producer,
        version=version,
        session_id=session_id,
        run_id=run_id,
        status=status,
        template_name="judge-defaults",
    )
    if not bootstrap:
        raise ValueError("no request_started facts were found to derive annotation defaults")
    default_payload = dict(bootstrap[0].payload)
    run_summary = _build_run_summary(facts=facts, artifacts=artifacts)

    normalized_provider = provider.strip().lower()
    warnings: list[str] = []
    raw_response: str | None = None
    parsed_response: dict[str, Any] | None = None
    if normalized_provider == "heuristic":
        warnings.append("judge provider heuristic: used bootstrap defaults without external model")
    elif normalized_provider == "openai-compatible":
        if not api_base:
            raise ValueError("--api-base is required for openai-compatible judge")
        if not api_key:
            raise ValueError("judge api key is required for openai-compatible provider")
        if not model:
            raise ValueError("--model is required for openai-compatible judge")
        raw_response, parsed_response = _call_openai_compatible_judge(
            api_base=api_base,
            api_key=api_key,
            model=model,
            run_summary=run_summary,
            default_payload=default_payload,
            instructions=instructions,
            timeout_seconds=timeout_seconds,
        )
    else:
        raise ValueError(f"unsupported judge provider: {provider}")

    merged_payload = _merge_annotation_payload(
        default_payload=default_payload,
        parsed_response=parsed_response,
        producer=producer,
        provider=normalized_provider,
        model=model,
        task_family=task_family,
        task_type=task_type,
        taxonomy_version=taxonomy_version,
        annotation_version=annotation_version,
        source_channel=source_channel,
        task_instance_key=task_instance_key,
        run_summary=run_summary,
        warnings=warnings,
    )
    review_reasons = _annotation_review_reasons(merged_payload)
    merged_payload["review_reasons"] = list(review_reasons)
    artifact = new_artifact_record(
        artifact_type="annotation",
        target_ref=f"run:{run_id}",
        producer=producer,
        payload=merged_payload,
        version=version,
        session_id=session_id,
        run_id=run_id,
        status=status,
        confidence=_float_value(merged_payload.get("quality_confidence")),
        supersedes_artifact_id=supersedes_artifact_id,
        metadata={
            "judge_provider": normalized_provider,
            "judge_model": model,
            "judge_input_version": "clawgraph.judge.run.v1",
            "review_reasons": list(review_reasons),
            "warnings": list(warnings),
        },
    )
    return JudgeAnnotationPlan(
        provider=normalized_provider,
        model=model,
        session_id=session_id,
        run_id=run_id,
        warnings=warnings,
        review_reasons=review_reasons,
        run_summary=run_summary,
        parsed_response=parsed_response,
        raw_response=raw_response,
        artifact=artifact,
    )


def plan_review_override(
    *,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
    producer: str,
    payload_patch: dict[str, Any] | None = None,
    version: str | None = None,
    status: str = "active",
    review_note: str | None = None,
    clear_review_reasons: bool = True,
) -> JudgeAnnotationPlan:
    """Plan one manual review override as a superseding annotation artifact."""

    if not facts:
        raise ValueError("no facts found")

    run_ids = sorted({fact.run_id for fact in facts})
    if len(run_ids) != 1:
        raise ValueError("manual override expects a single-run fact scope")
    session_ids = sorted({fact.session_id for fact in facts})
    if len(session_ids) != 1:
        raise ValueError("manual override expects a single-session fact scope")

    session_id = session_ids[0]
    run_id = run_ids[0]
    run_summary = _build_run_summary(facts=facts, artifacts=artifacts)
    current_annotation = _current_annotation_artifact(
        session_id=session_id,
        run_id=run_id,
        artifacts=artifacts,
    )
    if current_annotation is not None:
        default_payload = dict(current_annotation.payload)
        supersedes_artifact_id = current_annotation.artifact_id
    else:
        bootstrap = build_e1_annotation_artifacts(
            facts=facts,
            producer=producer,
            version=version,
            session_id=session_id,
            run_id=run_id,
            status=status,
            template_name="manual-override-defaults",
        )
        if not bootstrap:
            raise ValueError("no request_started facts were found to derive annotation defaults")
        default_payload = dict(bootstrap[0].payload)
        supersedes_artifact_id = None

    merged_payload = dict(default_payload)
    if payload_patch:
        merged_payload.update(
            {
                key: value
                for key, value in payload_patch.items()
                if value is not None
            }
        )
    merged_payload["annotation_kind"] = E1_ANNOTATION_KIND
    merged_payload["judge_provider"] = "human-review"
    merged_payload["review_note"] = review_note or _string_value(merged_payload.get("review_note"))
    if review_note:
        merged_payload["judge_summary"] = review_note
    else:
        merged_payload["judge_summary"] = (
            _string_value(merged_payload.get("judge_summary"))
            or "Manually reviewed and confirmed by operator."
        )
    if clear_review_reasons and "review_reasons" not in (payload_patch or {}):
        merged_payload["review_reasons"] = []
    else:
        merged_payload["review_reasons"] = _string_list(merged_payload.get("review_reasons"))
    if clear_review_reasons and "quality_confidence" not in (payload_patch or {}):
        merged_payload["quality_confidence"] = 1.0
    if clear_review_reasons and "verifier_score" not in (payload_patch or {}):
        merged_payload["verifier_score"] = 1.0
    merged_payload["task_family"] = _string_value(merged_payload.get("task_family")) or "captured_agent_task"
    merged_payload["task_type"] = _string_value(merged_payload.get("task_type")) or "generic_proxy_capture"
    merged_payload["task_instance_key"] = (
        _string_value(merged_payload.get("task_instance_key"))
        or f"run:{run_id}"
    )
    merged_payload["task_template_hash"] = _string_value(merged_payload.get("task_template_hash")) or "unknown"
    merged_payload["verifier_name"] = (
        _string_value(merged_payload.get("verifier_name"))
        or "human-review"
    )
    merged_payload["verifier_score"] = _clamp_score(merged_payload.get("verifier_score"), default=1.0)
    merged_payload["quality_confidence"] = _clamp_score(
        merged_payload.get("quality_confidence"),
        default=1.0 if clear_review_reasons else 0.9,
    )
    merged_payload["taxonomy_version"] = (
        _string_value(merged_payload.get("taxonomy_version"))
        or DEFAULT_TAXONOMY_VERSION
    )
    merged_payload["annotation_version"] = (
        _string_value(merged_payload.get("annotation_version"))
        or DEFAULT_ANNOTATION_VERSION
    )
    merged_payload["source_channel"] = (
        _string_value(merged_payload.get("source_channel"))
        or "captured"
    )
    warnings: list[str] = []
    missing_fields = [field for field in E1_REQUIRED_FIELDS if merged_payload.get(field) in {None, ""}]
    if missing_fields:
        raise ValueError(
            "manual override is missing required E1 fields: " + ", ".join(missing_fields)
        )
    review_reasons = _annotation_review_reasons(merged_payload)
    merged_payload["review_reasons"] = list(review_reasons)
    artifact = new_artifact_record(
        artifact_type="annotation",
        target_ref=f"run:{run_id}",
        producer=producer,
        payload=merged_payload,
        version=version,
        session_id=session_id,
        run_id=run_id,
        status=status,
        confidence=_float_value(merged_payload.get("quality_confidence")),
        supersedes_artifact_id=supersedes_artifact_id,
        metadata={
            "judge_provider": "human-review",
            "judge_model": None,
            "judge_input_version": "clawgraph.review.override.v1",
            "review_reasons": list(review_reasons),
            "warnings": warnings,
            "review_note": review_note,
            "source_annotation_artifact_id": supersedes_artifact_id,
        },
    )
    return JudgeAnnotationPlan(
        provider="human-review",
        model=None,
        session_id=session_id,
        run_id=run_id,
        warnings=warnings,
        review_reasons=review_reasons,
        run_summary=run_summary,
        parsed_response=payload_patch,
        raw_response=None,
        artifact=artifact,
    )


def _build_run_summary(
    *,
    facts: list[FactEvent],
    artifacts: list[ArtifactRecord],
) -> dict[str, Any]:
    request_summaries = build_request_span_summaries(facts, artifacts)
    branch_summaries = build_branch_inspect_summaries(facts, artifacts)
    request_fact_map = {
        (fact.request_id or fact.fact_id): fact
        for fact in facts
        if fact.kind == "request_started"
    }
    response_fact_map = {
        (fact.request_id or fact.fact_id): fact
        for fact in facts
        if fact.kind == "response_finished"
    }
    error_fact_map = {
        (fact.request_id or fact.fact_id): fact
        for fact in facts
        if fact.kind == "response_failed"
    }
    samples: list[dict[str, Any]] = []
    for summary in request_summaries[:3]:
        request_fact = request_fact_map.get(summary.request_id)
        response_fact = response_fact_map.get(summary.request_id) or error_fact_map.get(summary.request_id)
        samples.append(
            {
                "request_id": summary.request_id,
                "path": summary.path,
                "branch_id": summary.branch_id,
                "outcome": summary.outcome,
                "status_code": summary.status_code,
                "request_preview": _preview_from_fact(request_fact),
                "response_preview": _preview_from_fact(response_fact),
            }
        )
    semantic_kinds = sorted(
        {
            semantic_kind
            for fact in facts
            for semantic_kind in [_semantic_kind(fact)]
            if semantic_kind is not None
        }
    )
    return {
        "session_id": facts[0].session_id,
        "run_id": facts[0].run_id,
        "request_count": len(request_summaries),
        "success_count": sum(1 for summary in request_summaries if summary.outcome == "succeeded"),
        "failure_count": sum(1 for summary in request_summaries if summary.outcome == "failed"),
        "open_count": sum(1 for summary in request_summaries if summary.outcome == "open"),
        "branch_count": len(branch_summaries),
        "semantic_kinds": semantic_kinds,
        "request_samples": samples,
    }


def _preview_from_fact(fact: FactEvent | None) -> str | None:
    if fact is None:
        return None
    preview = fact.payload.get("preview")
    if isinstance(preview, str) and preview:
        return _truncate(redact_secret_like_text(preview) or preview)
    payload_json = fact.payload.get("json")
    if isinstance(payload_json, dict):
        if fact.kind == "request_started":
            messages = extract_prompt_messages(payload_json)
            if messages:
                content = "\n".join(
                    _truncate(redact_secret_like_text(str(message.get("content") or "")) or "")
                    for message in messages[:2]
                    if message.get("content")
                )
                if content:
                    return content
        if fact.kind == "response_finished":
            choices = payload_json.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") if isinstance(choices[0], dict) else None
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content:
                        return _truncate(redact_secret_like_text(content) or content)
        return _truncate(
            redact_secret_like_text(json.dumps(payload_json, ensure_ascii=True, sort_keys=True))
            or json.dumps(payload_json, ensure_ascii=True, sort_keys=True)
        )
    path = fact.payload.get("path")
    if isinstance(path, str) and path:
        return redact_secret_like_text(path)
    return None


def _call_openai_compatible_judge(
    *,
    api_base: str,
    api_key: str,
    model: str,
    run_summary: dict[str, Any],
    default_payload: dict[str, Any],
    instructions: str | None,
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    request_payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You classify generic agent trajectories for reusable training governance. "
                    "Return one JSON object and no markdown."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Create one E1 annotation for a generic agent run.",
                        "rules": [
                            "Do not assume benchmark-specific framework logic.",
                            "Prefer generic labels when uncertain.",
                            "Keep task_family/task_type reusable across agents.",
                            "quality_confidence and verifier_score must be 0..1 numbers.",
                            "If the run is incomplete, lower quality_confidence and include review_reasons.",
                        ],
                        "default_annotation": default_payload,
                        "run_summary": run_summary,
                        "required_keys": list(E1_REQUIRED_FIELDS)
                        + ["review_reasons", "judge_summary"],
                        "extra_instructions": instructions,
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                ),
            },
        ],
    }
    request = urllib.request.Request(
        api_base,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_response = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:  # pragma: no cover - exercised in integration
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"judge request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - exercised in integration
        raise ValueError(f"judge request failed: {exc.reason}") from exc

    try:
        response_payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise ValueError(f"judge response was not valid JSON: {raw_response[:200]}") from exc
    content = _message_content(response_payload)
    parsed = _extract_json_object(content)
    if not isinstance(parsed, dict):
        raise ValueError("judge response did not contain one JSON object")
    return content, parsed


def _message_content(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("judge response did not contain choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("judge response did not contain a message")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
        if parts:
            return "\n".join(parts)
    raise ValueError("judge response content was empty")


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    stripped = raw_text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[1]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _merge_annotation_payload(
    *,
    default_payload: dict[str, Any],
    parsed_response: dict[str, Any] | None,
    producer: str,
    provider: str,
    model: str | None,
    task_family: str | None,
    task_type: str | None,
    taxonomy_version: str | None,
    annotation_version: str | None,
    source_channel: str | None,
    task_instance_key: str | None,
    run_summary: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    parsed = parsed_response or {}
    merged = dict(default_payload)
    merged.update(
        {
            key: value
            for key, value in parsed.items()
            if value is not None
        }
    )
    merged["annotation_kind"] = E1_ANNOTATION_KIND
    merged["task_family"] = task_family or _string_value(merged.get("task_family")) or "captured_agent_task"
    merged["task_type"] = task_type or _string_value(merged.get("task_type")) or "generic_proxy_capture"
    merged["task_instance_key"] = (
        task_instance_key
        or _string_value(merged.get("task_instance_key"))
        or f"run:{run_summary['run_id']}"
    )
    merged["task_template_hash"] = _string_value(merged.get("task_template_hash")) or "unknown"
    default_verifier_name = f"{provider}:{model}" if model else f"{provider}:{producer}"
    merged["verifier_name"] = (
        _string_value(merged.get("verifier_name"))
        or default_verifier_name
    )
    merged["verifier_score"] = _clamp_score(merged.get("verifier_score"), default=0.5)
    merged["quality_confidence"] = _clamp_score(merged.get("quality_confidence"), default=0.5)
    merged["taxonomy_version"] = (
        taxonomy_version
        or _string_value(merged.get("taxonomy_version"))
        or DEFAULT_TAXONOMY_VERSION
    )
    merged["annotation_version"] = (
        annotation_version
        or _string_value(merged.get("annotation_version"))
        or DEFAULT_ANNOTATION_VERSION
    )
    merged["source_channel"] = (
        source_channel
        or _string_value(merged.get("source_channel"))
        or "captured"
    )
    merged["review_reasons"] = _string_list(merged.get("review_reasons"))
    merged["judge_summary"] = (
        _string_value(merged.get("judge_summary"))
        or "generic judge annotation"
    )
    merged["judge_provider"] = provider
    if model:
        merged["judge_model"] = model
    missing_fields = [field for field in E1_REQUIRED_FIELDS if merged.get(field) in {None, ""}]
    if missing_fields:
        warnings.append(f"judge output missing fields and fell back to defaults: {', '.join(missing_fields)}")
    return merged


def _annotation_review_reasons(payload: dict[str, Any]) -> list[str]:
    reasons = _string_list(payload.get("review_reasons"))
    quality_confidence = _float_value(payload.get("quality_confidence"))
    verifier_score = _float_value(payload.get("verifier_score"))
    if quality_confidence is not None and quality_confidence < 0.8:
        reasons.append("low_quality_confidence")
    if verifier_score is not None and verifier_score < 0.8:
        reasons.append("low_verifier_score")
    return list(dict.fromkeys(reasons))


def _current_annotation_artifact(
    *,
    session_id: str,
    run_id: str,
    artifacts: list[ArtifactRecord],
) -> ArtifactRecord | None:
    annotation_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.status == "active"
        and artifact.artifact_type == "annotation"
        and artifact.payload.get("annotation_kind") == E1_ANNOTATION_KIND
    ]
    _, artifact_ids = resolve_e1_annotation_for_run(
        session_id=session_id,
        run_id=run_id,
        artifacts=annotation_artifacts,
    )
    lookup = {artifact.artifact_id: artifact for artifact in annotation_artifacts}
    for artifact_id in reversed(artifact_ids):
        if artifact_id in lookup:
            return lookup[artifact_id]
    return None


def _semantic_kind(fact: FactEvent) -> str | None:
    if fact.kind != "semantic_event":
        return None
    value = fact.payload.get("semantic_kind")
    return value if isinstance(value, str) and value else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _clamp_score(value: Any, *, default: float) -> float:
    numeric = _float_value(value)
    if numeric is None:
        return default
    return max(0.0, min(1.0, round(numeric, 4)))


def _truncate(text: str, *, limit: int = 240) -> str:
    stripped = " ".join(text.split())
    if len(stripped) <= limit:
        return stripped
    return f"{stripped[: limit - 3]}..."
