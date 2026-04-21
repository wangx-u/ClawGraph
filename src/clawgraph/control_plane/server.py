"""Minimal control-plane service for ClawGraph dashboard and training actions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from clawgraph.control_plane.actions import (
    build_dashboard_bundle_action,
    create_handoff_action,
    evaluate_candidate_action,
    resolve_feedback_action,
    review_override_action,
    submit_training_request_action,
)

_AUTH_HEADER = "authorization"
_TOKEN_HEADER = "x-clawgraph-control-token"


@dataclass(slots=True)
class ControlPlaneConfig:
    host: str
    port: int
    store_uri: str
    manifest_dir: str | None = None
    auth_token: str | None = None
    actor: str = "clawgraph.control_plane"
    session_limit: int = 12
    run_limit: int = 24
    artifact_limit: int = 40


def _extract_token(headers: Any) -> str | None:
    auth_header = headers.get(_AUTH_HEADER)
    if isinstance(auth_header, str) and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    custom_token = headers.get(_TOKEN_HEADER)
    if isinstance(custom_token, str) and custom_token.strip():
        return custom_token.strip()
    return None


def _is_authorized(headers: Any, *, auth_token: str | None) -> bool:
    if auth_token is None:
        return False
    return _extract_token(headers) == auth_token


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = handler.headers.get("Content-Length")
    try:
        body_length = int(content_length or "0")
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
    body = handler.rfile.read(body_length) if body_length > 0 else b"{}"
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("request body must be valid json") from exc
    if not isinstance(payload, dict):
        raise ValueError("request body must be a json object")
    return payload


def _handle_exception(handler: BaseHTTPRequestHandler, error: Exception) -> None:
    status = HTTPStatus.BAD_REQUEST if isinstance(error, ValueError) else HTTPStatus.INTERNAL_SERVER_ERROR
    _json_response(
        handler,
        int(status),
        {"error": str(error) if isinstance(error, ValueError) else "internal server error"},
    )


def _build_handler(config: ControlPlaneConfig):
    class ControlPlaneHandler(BaseHTTPRequestHandler):
        server_version = "ClawGraphControlPlane/0.1"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlsplit(self.path)
            if parsed.path == "/healthz":
                _json_response(
                    self,
                    int(HTTPStatus.OK),
                    {"status": "ok", "actor": config.actor, "store_uri": config.store_uri},
                )
                return
            if parsed.path != "/api/dashboard/bundle":
                _json_response(self, int(HTTPStatus.NOT_FOUND), {"error": "not found"})
                return
            params = parse_qs(parsed.query)
            try:
                session_limit = int(params.get("session_limit", [config.session_limit])[0])
                run_limit = int(params.get("run_limit", [config.run_limit])[0])
                artifact_limit = int(params.get("artifact_limit", [config.artifact_limit])[0])
                bundle = build_dashboard_bundle_action(
                    store_uri=config.store_uri,
                    manifest_dir=config.manifest_dir,
                    session_limit=session_limit,
                    run_limit=run_limit,
                    artifact_limit=artifact_limit,
                )
            except Exception as exc:  # pragma: no cover - exercised via tests/integration
                _handle_exception(self, exc)
                return
            _json_response(
                self,
                int(HTTPStatus.OK),
                {
                    "bundle": bundle,
                    "meta": {
                        "provider": "control-plane",
                        "status": "prod",
                        "statusText": "当前使用 ClawGraph control-plane 服务",
                        "supportsMutations": config.auth_token is not None,
                        "actor": config.actor,
                    },
                },
            )

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlsplit(self.path)
            if not _is_authorized(self.headers, auth_token=config.auth_token):
                _json_response(
                    self,
                    int(HTTPStatus.UNAUTHORIZED),
                    {"error": "control-plane authentication failed"},
                )
                return
            try:
                payload = _read_json_body(self)
                if parsed.path == "/api/dashboard/feedback/resolve":
                    feedback_id = payload.get("feedbackId")
                    status = payload.get("status")
                    if not isinstance(feedback_id, str) or not feedback_id:
                        raise ValueError("feedbackId is required")
                    if status not in {"reviewed", "resolved"}:
                        raise ValueError("status must be reviewed or resolved")
                    result = resolve_feedback_action(
                        store_uri=config.store_uri,
                        feedback_id=feedback_id,
                        status=status,
                        note=payload.get("note") if isinstance(payload.get("note"), str) else None,
                        reviewer=config.actor,
                    )
                elif parsed.path == "/api/dashboard/feedback/review-override":
                    session_id = payload.get("sessionId")
                    run_id = payload.get("runId")
                    if not isinstance(session_id, str) or not session_id:
                        raise ValueError("sessionId is required")
                    if not isinstance(run_id, str) or not run_id:
                        raise ValueError("runId is required")
                    result = review_override_action(
                        store_uri=config.store_uri,
                        session_id=session_id,
                        run_id=run_id,
                        feedback_id=payload.get("feedbackId")
                        if isinstance(payload.get("feedbackId"), str)
                        else None,
                        feedback_status=payload.get("feedbackStatus")
                        if isinstance(payload.get("feedbackStatus"), str)
                        else "resolved",
                        review_note=payload.get("reviewNote")
                        if isinstance(payload.get("reviewNote"), str)
                        else None,
                        reviewer=config.actor,
                        quality_confidence=float(payload.get("qualityConfidence", 1.0)),
                        verifier_score=float(payload.get("verifierScore", 1.0)),
                    )
                elif parsed.path == "/api/training/submit":
                    result = submit_training_request_action(
                        store_uri=config.store_uri,
                        manifest_dir=config.manifest_dir,
                        request_id=payload.get("requestId")
                        if isinstance(payload.get("requestId"), str)
                        else None,
                        manifest_path=payload.get("manifestPath")
                        if isinstance(payload.get("manifestPath"), str)
                        else None,
                        executor_ref=payload.get("executorRef")
                        if isinstance(payload.get("executorRef"), str)
                        else None,
                        candidate_out=payload.get("candidateOut")
                        if isinstance(payload.get("candidateOut"), str)
                        else None,
                    )
                elif parsed.path == "/api/training/evaluate":
                    result = evaluate_candidate_action(
                        store_uri=config.store_uri,
                        manifest_dir=config.manifest_dir,
                        candidate_id=payload.get("candidateId")
                        if isinstance(payload.get("candidateId"), str)
                        else None,
                        manifest_path=payload.get("manifestPath")
                        if isinstance(payload.get("manifestPath"), str)
                        else None,
                        eval_suite_id=payload.get("evalSuiteId")
                        if isinstance(payload.get("evalSuiteId"), str)
                        else None,
                        baseline_model=payload.get("baselineModel")
                        if isinstance(payload.get("baselineModel"), str)
                        else None,
                        baseline_model_path=payload.get("baselineModelPath")
                        if isinstance(payload.get("baselineModelPath"), str)
                        else None,
                        sample_ref=payload.get("sampleRef")
                        if isinstance(payload.get("sampleRef"), str)
                        else None,
                        grader_name=payload.get("graderName")
                        if isinstance(payload.get("graderName"), str)
                        else "exact-match",
                        grader_ref=payload.get("graderRef")
                        if isinstance(payload.get("graderRef"), str)
                        else None,
                        thresholds=payload.get("thresholds")
                        if isinstance(payload.get("thresholds"), dict)
                        else None,
                        max_tokens=int(payload.get("maxTokens", 512)),
                        temperature=float(payload.get("temperature", 0.0)),
                        top_p=float(payload.get("topP", 1.0)),
                        base_url=payload.get("baseUrl")
                        if isinstance(payload.get("baseUrl"), str)
                        else None,
                        scorecard_metadata=payload.get("scorecardMetadata")
                        if isinstance(payload.get("scorecardMetadata"), dict)
                        else None,
                        record_promotion=bool(payload.get("recordPromotion", True)),
                        promotion_stage=payload.get("promotionStage")
                        if isinstance(payload.get("promotionStage"), str)
                        else "offline",
                        coverage_policy_version=payload.get("coveragePolicyVersion")
                        if isinstance(payload.get("coveragePolicyVersion"), str)
                        else "logits.eval.v1",
                        promotion_summary=payload.get("promotionSummary")
                        if isinstance(payload.get("promotionSummary"), str)
                        else None,
                        rollback_conditions=payload.get("rollbackConditions")
                        if isinstance(payload.get("rollbackConditions"), list)
                        else None,
                        output_path=payload.get("outputPath")
                        if isinstance(payload.get("outputPath"), str)
                        else None,
                    )
                elif parsed.path == "/api/training/handoff":
                    result = create_handoff_action(
                        store_uri=config.store_uri,
                        manifest_dir=config.manifest_dir,
                        candidate_id=payload.get("candidateId")
                        if isinstance(payload.get("candidateId"), str)
                        else None,
                        manifest_path=payload.get("manifestPath")
                        if isinstance(payload.get("manifestPath"), str)
                        else None,
                        promotion_decision_id=payload.get("promotionDecisionId")
                        if isinstance(payload.get("promotionDecisionId"), str)
                        else None,
                        metadata=payload.get("metadata")
                        if isinstance(payload.get("metadata"), dict)
                        else None,
                        output_path=payload.get("outputPath")
                        if isinstance(payload.get("outputPath"), str)
                        else None,
                    )
                else:
                    _json_response(self, int(HTTPStatus.NOT_FOUND), {"error": "not found"})
                    return
            except Exception as exc:  # pragma: no cover - exercised via tests/integration
                _handle_exception(self, exc)
                return
            _json_response(self, int(HTTPStatus.OK), result)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    return ControlPlaneHandler


def run_control_plane_server(config: ControlPlaneConfig) -> None:
    server = ThreadingHTTPServer((config.host, config.port), _build_handler(config))
    print(
        "ClawGraph control-plane listening on "
        f"http://{config.host}:{config.port} (store={config.store_uri})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
