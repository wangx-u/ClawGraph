"""Runtime validation for persisted protocol records."""

from __future__ import annotations

from typing import Any

from clawgraph.protocol.models import ArtifactRecord, FactEvent

_LEGACY_BODY_REF_ENCODINGS = {"gzip", None}


def validate_fact_event(fact: FactEvent) -> None:
    """Validate one fact event before it is persisted."""

    _require_non_empty_string(fact.fact_id, label="fact_id")
    _require_non_empty_string(fact.schema_version, label="schema_version")
    _require_non_empty_string(fact.run_id, label="run_id")
    _require_non_empty_string(fact.session_id, label="session_id")
    _require_non_empty_string(fact.actor, label="actor")
    _require_non_empty_string(fact.kind, label="kind")
    if not isinstance(fact.payload, dict):
        raise ValueError("fact payload must be a JSON object")
    if not isinstance(fact.metadata, dict):
        raise ValueError("fact metadata must be a JSON object")
    _validate_common_fact_payload(fact.payload)
    if fact.kind == "semantic_event":
        _validate_semantic_event_payload(fact.payload)


def validate_artifact_record(artifact: ArtifactRecord) -> None:
    """Validate one artifact record before it is persisted."""

    _require_non_empty_string(artifact.artifact_id, label="artifact_id")
    _require_non_empty_string(artifact.schema_version, label="schema_version")
    _require_non_empty_string(artifact.artifact_type, label="artifact_type")
    _require_non_empty_string(artifact.target_ref, label="target_ref")
    _require_non_empty_string(artifact.producer, label="producer")
    _require_non_empty_string(artifact.status, label="status")
    if not isinstance(artifact.payload, dict):
        raise ValueError("artifact payload must be a JSON object")
    if not isinstance(artifact.metadata, dict):
        raise ValueError("artifact metadata must be a JSON object")
    if artifact.confidence is not None and (
        not isinstance(artifact.confidence, (int, float)) or isinstance(artifact.confidence, bool)
    ):
        raise ValueError("artifact confidence must be numeric when provided")


def validate_body_ref(body_ref: dict[str, Any]) -> None:
    """Validate one sidecar body reference."""

    storage = body_ref.get("storage")
    if storage != "local_file":
        raise ValueError("body_ref storage must be 'local_file'")
    relative_path = body_ref.get("relative_path")
    absolute_path = body_ref.get("path")
    if not isinstance(relative_path, str) and not isinstance(absolute_path, str):
        raise ValueError("body_ref must include a relative_path or path")
    if isinstance(relative_path, str) and not relative_path:
        raise ValueError("body_ref relative_path must not be empty")
    if isinstance(absolute_path, str) and not absolute_path:
        raise ValueError("body_ref path must not be empty")
    encoding = body_ref.get("encoding")
    if encoding not in _LEGACY_BODY_REF_ENCODINGS:
        raise ValueError("body_ref encoding must be gzip when provided")
    content_type = body_ref.get("content_type")
    if content_type is not None and not isinstance(content_type, str):
        raise ValueError("body_ref content_type must be a string when provided")
    for key in ("byte_size", "compressed_size"):
        value = body_ref.get(key)
        if value is None:
            continue
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"body_ref {key} must be a non-negative integer when provided")
    sha256 = body_ref.get("sha256")
    if sha256 is not None and (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
    ):
        raise ValueError("body_ref sha256 must be a lowercase 64-character hex string")


def _validate_common_fact_payload(payload: dict[str, Any]) -> None:
    body_ref = payload.get("body_ref")
    if isinstance(body_ref, dict):
        validate_body_ref(body_ref)
    elif body_ref is not None:
        raise ValueError("body_ref must be a JSON object when provided")

    headers = payload.get("headers")
    if headers is not None and not isinstance(headers, dict):
        raise ValueError("fact payload headers must be a JSON object when provided")

    if "input_messages" in payload:
        input_messages = payload.get("input_messages")
        if not isinstance(input_messages, list) or any(
            not isinstance(item, dict) for item in input_messages
        ):
            raise ValueError("fact payload input_messages must be a list of message objects")

    request_fingerprint = payload.get("request_fingerprint")
    if request_fingerprint is not None and not isinstance(request_fingerprint, str):
        raise ValueError("fact payload request_fingerprint must be a string when provided")

    canonical = payload.get("canonical")
    if canonical is not None and not isinstance(canonical, dict):
        raise ValueError("fact payload canonical must be a JSON object when provided")


def _validate_semantic_event_payload(payload: dict[str, Any]) -> None:
    semantic_kind = payload.get("semantic_kind")
    if not isinstance(semantic_kind, str) or not semantic_kind:
        raise ValueError("semantic_event payload semantic_kind is required")
    nested_payload = payload.get("payload")
    if not isinstance(nested_payload, dict):
        raise ValueError("semantic_event payload payload must be a JSON object")
    fact_ref = payload.get("fact_ref")
    if fact_ref is not None and (not isinstance(fact_ref, str) or not fact_ref):
        raise ValueError("semantic_event payload fact_ref must be a non-empty string when provided")


def _require_non_empty_string(value: Any, *, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
