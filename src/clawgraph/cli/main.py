"""CLI entrypoint for ClawGraph."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from clawgraph.artifacts import plan_artifact_bootstrap
from clawgraph.bootstrap import bootstrap_openclaw_session
from clawgraph.curation import freeze_cohort, list_slice_candidates, preview_slice_review_queue
from clawgraph.control_plane import ControlPlaneConfig, run_control_plane_server
from clawgraph.dashboard import (
    build_dashboard_snapshot,
    inspect_run_workflow,
    render_dashboard_snapshot,
)
from clawgraph.export import (
    build_dataset_readiness_summary,
    export_dataset,
    plan_dataset_export,
    plan_dataset_export_for_scope,
    render_dataset_readiness,
)
from clawgraph.evaluation import (
    create_eval_suite_from_cohort,
    enqueue_feedback,
    record_promotion_decision,
    record_scorecard,
    sync_feedback_queue_from_slice_review,
    update_feedback_queue_status,
)
from clawgraph.graph import (
    build_branch_inspect_summaries,
    build_request_span_summaries,
    build_session_inspect_summary,
    correlate_request_groups,
    get_branch_inspect_summary,
    get_request_span_summary,
    infer_branches,
    render_branch_inspect,
    render_request_inspect,
    render_session_inspect,
    render_session_replay,
)
from clawgraph.integrations.logits import (
    build_training_registry,
    create_router_handoff_manifest,
    describe_logits_runtime,
    evaluate_candidate_on_suite,
    load_manifest as load_logits_manifest,
    prepare_dpo_training_request,
    prepare_rl_training_request,
    prepare_sft_training_request,
    render_training_registry,
    submit_training_request,
)
from clawgraph.integrations.logits.manifests import (
    ModelCandidateManifest,
    TrainingRequestManifest,
)
from clawgraph.judge import plan_judge_annotation, plan_review_override
from clawgraph.phase2 import run_phase2_workflow
from clawgraph.protocol.factories import (
    new_artifact_record,
    new_semantic_event_fact,
    new_slice_record,
)
from clawgraph.proxy import ProxyConfig, run_proxy_server
from clawgraph.proxy.payload_store import LocalPayloadStore
from clawgraph.query import ClawGraphQueryService
from clawgraph.store import SQLiteFactStore


DEFAULT_STORE_URI = "sqlite:///clawgraph.db"


def _infer_session_id_from_target_ref(target_ref: str) -> str | None:
    if target_ref.startswith("session:"):
        return target_ref.split(":", 1)[1]
    return None


def _infer_run_id_from_target_ref(target_ref: str) -> str | None:
    if target_ref.startswith("run:"):
        return target_ref.split(":", 1)[1]
    return None


def _resolve_session_id_for_run(*, store: SQLiteFactStore, run_id: str) -> str | None:
    return ClawGraphQueryService(store=store).resolve_session_id(run_id=run_id)


def _load_json_argument(raw_value: str, *, label: str) -> dict:
    payload = _load_json_value(raw_value, label=label)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _load_json_value(raw_value: str, *, label: str) -> Any:
    if raw_value.startswith("@"):
        payload_text = Path(raw_value[1:]).read_text(encoding="utf-8")
    else:
        payload_text = raw_value
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON") from exc


def _load_text_argument(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    if raw_value.startswith("@"):
        return Path(raw_value[1:]).read_text(encoding="utf-8")
    return raw_value


def _resolve_target_ref(
    *,
    store: SQLiteFactStore,
    target_ref: str,
    session_value: str | None,
    run_value: str | None = None,
) -> tuple[str, str | None]:
    if target_ref == "session:latest":
        session_id = _resolve_scope_session_id(store=store, session_value=session_value, run_id=run_value)
        if session_id is None and run_value is not None:
            facts = store.list_facts(run_id=run_value)
            if not facts:
                raise ValueError("no facts found in scope")
            session_id = facts[0].session_id
        if session_id is None:
            raise ValueError("no sessions found in store")
        return f"session:{session_id}", session_id

    if target_ref == "run:latest":
        effective_run_id = _resolve_scope_run_id(
            store=store,
            session_value=session_value,
            run_value=run_value,
            default_latest_run=True,
        )
        if effective_run_id is None:
            raise ValueError("no runs found in scope")
        session_id = _resolve_session_id_for_run(store=store, run_id=effective_run_id)
        return f"run:{effective_run_id}", session_id

    if target_ref in {
        "latest-response",
        "latest-model-response",
        "latest-tool-response",
        "latest-failed-branch",
        "latest-succeeded-branch",
    }:
        session_id = _resolve_scope_session_id(
            store=store,
            session_value=session_value,
            run_id=run_value,
        )
        effective_run_id = _resolve_scope_run_id(
            store=store,
            session_value=session_value,
            run_value=run_value,
            default_latest_run=True,
        )
        facts = store.list_facts(session_id=session_id, run_id=effective_run_id)
        if not facts:
            raise ValueError("no facts found in scope")
        if target_ref in {"latest-response", "latest-model-response", "latest-tool-response"}:
            preferred_actor = (
                "model"
                if target_ref in {"latest-response", "latest-model-response"}
                else "tool"
            )
            for fact in reversed(facts):
                if fact.kind == "response_finished" and fact.actor == preferred_actor:
                    return f"fact:{fact.fact_id}", facts[0].session_id
            if target_ref == "latest-response":
                for fact in reversed(facts):
                    if fact.kind == "response_finished":
                        return f"fact:{fact.fact_id}", facts[0].session_id
            raise ValueError("no response_finished facts found")

        branches = build_branch_inspect_summaries(facts)
        desired_status = "failed" if target_ref == "latest-failed-branch" else "succeeded"
        for branch in reversed(branches):
            if branch.status == desired_status and branch.branch_type != "mainline":
                return f"branch:{branch.branch_id}", facts[0].session_id
        raise ValueError(f"no {desired_status} non-mainline branches found")

    if target_ref.startswith("session:") and target_ref.endswith("latest"):
        session_id = _resolve_scope_session_id(store=store, session_value=session_value, run_id=run_value)
        if session_id is None and run_value is not None:
            facts = store.list_facts(run_id=run_value)
            if not facts:
                raise ValueError("no facts found in scope")
            session_id = facts[0].session_id
        if session_id is None:
            raise ValueError("no sessions found in store")
        return f"session:{session_id}", session_id

    if target_ref.startswith("run:"):
        session_id = _resolve_session_id_for_run(
            store=store,
            run_id=target_ref.split(":", 1)[1],
        )
        return target_ref, session_id
    return target_ref, session_value


def _resolve_scope_session_id(
    *,
    store: SQLiteFactStore,
    session_value: str | None,
    run_id: str | None = None,
) -> str | None:
    return ClawGraphQueryService(store=store).resolve_session_id(
        session=session_value,
        run_id=run_id,
    )


def _resolve_scope_run_id(
    *,
    store: SQLiteFactStore,
    session_value: str | None,
    run_value: str | None,
    default_latest_run: bool = False,
) -> str | None:
    return ClawGraphQueryService(store=store).resolve_run_id(
        session=session_value,
        run_id=run_value,
        default_latest_run=default_latest_run,
    )


def _load_facts_for_scope(
    *,
    store: SQLiteFactStore,
    session_value: str | None,
    run_id: str | None = None,
    default_latest_run: bool = False,
) -> tuple[str, list]:
    scope = ClawGraphQueryService(store=store).load_scope(
        session=session_value,
        run_id=run_id,
        default_latest_run=default_latest_run,
    )
    return scope.session_id, scope.facts


def _artifact_signature(artifact) -> str:
    return json.dumps(
        {
            "artifact_type": artifact.artifact_type,
            "target_ref": artifact.target_ref,
            "producer": artifact.producer,
            "version": artifact.version,
            "session_id": artifact.session_id,
            "run_id": artifact.run_id,
            "status": artifact.status,
            "confidence": artifact.confidence,
            "supersedes_artifact_id": artifact.supersedes_artifact_id,
            "payload": artifact.payload,
            "metadata": artifact.metadata,
        },
        ensure_ascii=True,
        sort_keys=True,
    )


def _default_export_output_path(*, session_id: str, builder: str, run_id: str | None) -> Path:
    safe_session = session_id.replace("/", "_")
    safe_builder = builder.replace("/", "_")
    if run_id:
        safe_run = run_id.replace("/", "_")
        filename = f"{safe_session}.{safe_run}.{safe_builder}.jsonl"
    else:
        filename = f"{safe_session}.{safe_builder}.jsonl"
    return Path("out") / filename


def _persist_unique_artifacts(
    *,
    store: SQLiteFactStore,
    session_id: str,
    run_id: str | None,
    artifacts: list,
) -> tuple[list, int]:
    existing_artifacts = store.list_artifacts(
        session_id=session_id,
        run_id=run_id,
        latest_only=True,
    )
    seen_signatures = {_artifact_signature(artifact) for artifact in existing_artifacts}
    persisted_artifacts = []
    skipped_count = 0
    for artifact in artifacts:
        signature = _artifact_signature(artifact)
        if signature in seen_signatures:
            skipped_count += 1
            continue
        persisted_artifacts.append(artifact)
        seen_signatures.add(signature)
    if persisted_artifacts:
        store.append_artifacts(persisted_artifacts)
    return persisted_artifacts, skipped_count


def _body_ref_from_fact_payload(payload: dict) -> dict | None:
    body_ref = payload.get("body_ref")
    if isinstance(body_ref, dict):
        return body_ref
    return None


def _decode_body_payload(body: bytes) -> tuple[str, dict | list | None]:
    text = body.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text, None
    if isinstance(parsed, (dict, list)):
        return text, parsed
    return text, None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawgraph")
    subparsers = parser.add_subparsers(dest="command")

    proxy = subparsers.add_parser("proxy", help="Start the proxy server")
    proxy.add_argument("--model-upstream")
    proxy.add_argument("--tool-upstream")
    proxy.add_argument("--store", default=DEFAULT_STORE_URI)
    proxy.add_argument("--host", default="127.0.0.1")
    proxy.add_argument("--port", type=int, default=8080)
    proxy.add_argument("--auth-token")
    proxy.add_argument("--upstream-api-key")
    proxy.add_argument("--max-request-body-bytes", type=int, default=1024 * 1024)
    proxy.add_argument("--max-response-body-bytes", type=int, default=4 * 1024 * 1024)
    proxy.add_argument("--max-capture-bytes", type=int, default=16 * 1024)
    proxy.add_argument("--max-stream-chunk-facts", type=int, default=32)
    proxy.add_argument("--disable-session-user-binding", action="store_true")
    proxy.add_argument("--payload-dir")

    control_plane = subparsers.add_parser(
        "control-plane",
        help="Run the ClawGraph control-plane service",
    )
    control_plane_subparsers = control_plane.add_subparsers(dest="control_plane_command")

    control_plane_serve = control_plane_subparsers.add_parser(
        "serve",
        help="Start the control-plane HTTP service",
    )
    control_plane_serve.add_argument("--store", default=DEFAULT_STORE_URI)
    control_plane_serve.add_argument("--manifest-dir")
    control_plane_serve.add_argument("--host", default="127.0.0.1")
    control_plane_serve.add_argument("--port", type=int, default=8096)
    control_plane_serve.add_argument("--auth-token")
    control_plane_serve.add_argument("--actor", default="clawgraph.control_plane")
    control_plane_serve.add_argument("--session-limit", type=int, default=12)
    control_plane_serve.add_argument("--run-limit", type=int, default=24)
    control_plane_serve.add_argument("--artifact-limit", type=int, default=40)

    payload = subparsers.add_parser("payload", help="Read or garbage-collect spilled payload sidecars")
    payload_subparsers = payload.add_subparsers(dest="payload_command")

    payload_read = payload_subparsers.add_parser("read", help="Read one spilled payload body")
    payload_read.add_argument("--store", default=DEFAULT_STORE_URI)
    payload_read.add_argument("--payload-dir")
    payload_read.add_argument("--fact-id", required=True)
    payload_read.add_argument("--json", action="store_true")

    payload_gc = payload_subparsers.add_parser("gc", help="Garbage-collect unreferenced payload sidecars")
    payload_gc.add_argument("--store", default=DEFAULT_STORE_URI)
    payload_gc.add_argument("--payload-dir")
    payload_gc.add_argument("--dry-run", action="store_true")
    payload_gc.add_argument("--grace-seconds", type=int, default=300)
    payload_gc.add_argument("--json", action="store_true")

    replay = subparsers.add_parser("replay", help="Inspect a session replay")
    replay.add_argument("--session", default="latest")
    replay.add_argument("--run-id")
    replay.add_argument("--store", default=DEFAULT_STORE_URI)
    replay.add_argument("--json", action="store_true")

    branches = subparsers.add_parser("branches", help="Inspect inferred branches")
    branches.add_argument("--session", default="latest")
    branches.add_argument("--run-id")
    branches.add_argument("--store", default=DEFAULT_STORE_URI)
    branches.add_argument("--json", action="store_true")

    inspect = subparsers.add_parser("inspect", help="Inspect operational and learning views")
    inspect_subparsers = inspect.add_subparsers(dest="inspect_command")

    inspect_session = inspect_subparsers.add_parser("session", help="Inspect a session summary")
    inspect_session.add_argument("--session", default="latest")
    inspect_session.add_argument("--run-id")
    inspect_session.add_argument("--store", default=DEFAULT_STORE_URI)
    inspect_session.add_argument("--json", action="store_true")

    inspect_request = inspect_subparsers.add_parser("request", help="Inspect one request span")
    inspect_request.add_argument("--request-id", required=True)
    inspect_request.add_argument("--session", default="latest")
    inspect_request.add_argument("--run-id")
    inspect_request.add_argument("--store", default=DEFAULT_STORE_URI)
    inspect_request.add_argument("--json", action="store_true")

    inspect_branch = inspect_subparsers.add_parser("branch", help="Inspect one branch")
    inspect_branch.add_argument("--session", default="latest")
    inspect_branch.add_argument("--run-id")
    inspect_branch.add_argument("--branch-id")
    inspect_branch.add_argument("--store", default=DEFAULT_STORE_URI)
    inspect_branch.add_argument("--json", action="store_true")

    inspect_workflow = inspect_subparsers.add_parser(
        "workflow",
        help="Inspect the phase-2 workflow/gate status for one run",
    )
    inspect_workflow.add_argument("--session", default="latest")
    inspect_workflow.add_argument("--run-id")
    inspect_workflow.add_argument("--store", default=DEFAULT_STORE_URI)
    inspect_workflow.add_argument("--builder")
    inspect_workflow.add_argument("--json", action="store_true")

    inspect_dashboard = inspect_subparsers.add_parser(
        "dashboard",
        help="Inspect a dashboard-oriented snapshot across execution and governance objects",
    )
    inspect_dashboard.add_argument("--store", default=DEFAULT_STORE_URI)
    inspect_dashboard.add_argument("--builder")
    inspect_dashboard.add_argument("--session-limit", type=int, default=10)
    inspect_dashboard.add_argument("--run-limit", type=int, default=20)
    inspect_dashboard.add_argument("--watch", action="store_true")
    inspect_dashboard.add_argument("--interval-seconds", type=float, default=2.0)
    inspect_dashboard.add_argument("--iterations", type=int)
    inspect_dashboard.add_argument("--json", action="store_true")

    list_parser = subparsers.add_parser("list", help="List sessions, requests, or facts")
    list_subparsers = list_parser.add_subparsers(dest="list_command")
    list_sessions = list_subparsers.add_parser("sessions", help="List known sessions")
    list_sessions.add_argument("--store", default=DEFAULT_STORE_URI)
    list_sessions.add_argument("--json", action="store_true")

    list_runs = list_subparsers.add_parser("runs", help="List runs for a session")
    list_runs.add_argument("--session", default="latest")
    list_runs.add_argument("--store", default=DEFAULT_STORE_URI)
    list_runs.add_argument("--json", action="store_true")

    list_requests = list_subparsers.add_parser("requests", help="List request spans for a session")
    list_requests.add_argument("--session", default="latest")
    list_requests.add_argument("--run-id")
    list_requests.add_argument("--store", default=DEFAULT_STORE_URI)
    list_requests.add_argument("--json", action="store_true")

    list_facts = list_subparsers.add_parser("facts", help="List facts for a session")
    list_facts.add_argument("--session", default="latest")
    list_facts.add_argument("--run-id")
    list_facts.add_argument("--store", default=DEFAULT_STORE_URI)
    list_facts.add_argument("--kind")
    list_facts.add_argument("--actor")
    list_facts.add_argument("--json", action="store_true")

    list_readiness = list_subparsers.add_parser(
        "readiness",
        help="List builder readiness across recent runs",
    )
    list_readiness.add_argument("--store", default=DEFAULT_STORE_URI)
    list_readiness.add_argument("--builder")
    list_readiness.add_argument("--limit", type=int, default=20)
    list_readiness.add_argument("--json", action="store_true")

    slice_parser = subparsers.add_parser("slice", help="Manage slice registry and candidate pools")
    slice_subparsers = slice_parser.add_subparsers(dest="slice_command")

    slice_register = slice_subparsers.add_parser("register", help="Create or update a slice")
    slice_register.add_argument("--store", default=DEFAULT_STORE_URI)
    slice_register.add_argument("--slice-id", required=True)
    slice_register.add_argument("--task-family", required=True)
    slice_register.add_argument("--task-type", required=True)
    slice_register.add_argument("--taxonomy-version", required=True)
    slice_register.add_argument("--sample-unit", required=True)
    slice_register.add_argument("--verifier-contract", required=True)
    slice_register.add_argument("--risk-level", required=True)
    slice_register.add_argument("--default-use", required=True)
    slice_register.add_argument("--owner", required=True)
    slice_register.add_argument("--description")
    slice_register.add_argument("--metadata", default="{}")
    slice_register.add_argument("--json", action="store_true")

    slice_list = slice_subparsers.add_parser("list", help="List registered slices")
    slice_list.add_argument("--store", default=DEFAULT_STORE_URI)
    slice_list.add_argument("--task-family")
    slice_list.add_argument("--task-type")
    slice_list.add_argument("--taxonomy-version")
    slice_list.add_argument("--default-use")
    slice_list.add_argument("--json", action="store_true")

    slice_candidates = slice_subparsers.add_parser(
        "candidates",
        help="Resolve the candidate pool for one registered slice",
    )
    slice_candidates.add_argument("--store", default=DEFAULT_STORE_URI)
    slice_candidates.add_argument("--slice-id", required=True)
    slice_candidates.add_argument("--session")
    slice_candidates.add_argument("--run-id")
    slice_candidates.add_argument("--task-instance-key")
    slice_candidates.add_argument("--task-template-hash")
    slice_candidates.add_argument("--min-quality-confidence", type=float)
    slice_candidates.add_argument("--min-verifier-score", type=float)
    slice_candidates.add_argument("--source-channel")
    slice_candidates.add_argument("--limit", type=int)
    slice_candidates.add_argument("--json", action="store_true")

    cohort = subparsers.add_parser("cohort", help="Freeze and inspect cohorts")
    cohort_subparsers = cohort.add_subparsers(dest="cohort_command")

    cohort_freeze = cohort_subparsers.add_parser("freeze", help="Freeze a cohort from a slice candidate pool")
    cohort_freeze.add_argument("--store", default=DEFAULT_STORE_URI)
    cohort_freeze.add_argument("--slice-id", required=True)
    cohort_freeze.add_argument("--name")
    cohort_freeze.add_argument("--cohort-id")
    cohort_freeze.add_argument("--session")
    cohort_freeze.add_argument("--run-id")
    cohort_freeze.add_argument("--task-instance-key")
    cohort_freeze.add_argument("--task-template-hash")
    cohort_freeze.add_argument("--min-quality-confidence", type=float)
    cohort_freeze.add_argument("--min-verifier-score", type=float)
    cohort_freeze.add_argument("--source-channel")
    cohort_freeze.add_argument("--limit", type=int)
    cohort_freeze.add_argument("--json", action="store_true")

    cohort_list = cohort_subparsers.add_parser("list", help="List frozen cohorts")
    cohort_list.add_argument("--store", default=DEFAULT_STORE_URI)
    cohort_list.add_argument("--slice-id")
    cohort_list.add_argument("--status")
    cohort_list.add_argument("--json", action="store_true")

    cohort_show = cohort_subparsers.add_parser("show", help="Show one frozen cohort")
    cohort_show.add_argument("--store", default=DEFAULT_STORE_URI)
    cohort_show.add_argument("--cohort-id", required=True)
    cohort_show.add_argument("--json", action="store_true")

    bootstrap = subparsers.add_parser("bootstrap", help="Seed a first-run session into the store")
    bootstrap_subparsers = bootstrap.add_subparsers(dest="bootstrap_command")
    bootstrap_openclaw = bootstrap_subparsers.add_parser(
        "openclaw",
        help="Seed an OpenClaw-style session with facts, semantics, and artifacts",
    )
    bootstrap_openclaw.add_argument("--store", default=DEFAULT_STORE_URI)
    bootstrap_openclaw.add_argument("--session-id")
    bootstrap_openclaw.add_argument("--run-id")
    bootstrap_openclaw.add_argument("--user-id", default="user_seed")
    bootstrap_openclaw.add_argument("--json", action="store_true")

    semantic = subparsers.add_parser("semantic", help="Append semantic runtime events")
    semantic_subparsers = semantic.add_subparsers(dest="semantic_command")
    semantic_append = semantic_subparsers.add_parser("append", help="Append a semantic event")
    semantic_append.add_argument("--store", default=DEFAULT_STORE_URI)
    semantic_append.add_argument("--session-id", required=True)
    semantic_append.add_argument("--run-id", required=True)
    semantic_append.add_argument("--kind", required=True, dest="semantic_kind")
    semantic_append.add_argument("--fact-ref")
    semantic_append.add_argument("--payload", default="{}")
    semantic_append.add_argument("--request-id")
    semantic_append.add_argument("--user-id")
    semantic_append.add_argument("--thread-id")
    semantic_append.add_argument("--task-id")
    semantic_append.add_argument("--branch-id")

    judge = subparsers.add_parser("judge", help="Plan and append judge-produced annotations")
    judge_subparsers = judge.add_subparsers(dest="judge_command")
    judge_annotate = judge_subparsers.add_parser(
        "annotate",
        help="Plan one run-level E1 annotation from a heuristic or OpenAI-compatible judge",
    )
    judge_annotate.add_argument("--store", default=DEFAULT_STORE_URI)
    judge_annotate.add_argument("--session", default="latest")
    judge_annotate.add_argument("--run-id")
    judge_annotate.add_argument("--provider", default="heuristic")
    judge_annotate.add_argument("--model")
    judge_annotate.add_argument("--api-base")
    judge_annotate.add_argument("--api-key")
    judge_annotate.add_argument("--api-key-env", default="OPENAI_API_KEY")
    judge_annotate.add_argument("--producer")
    judge_annotate.add_argument("--version")
    judge_annotate.add_argument("--status", default="active")
    judge_annotate.add_argument("--task-family")
    judge_annotate.add_argument("--task-type")
    judge_annotate.add_argument("--taxonomy-version")
    judge_annotate.add_argument("--annotation-version")
    judge_annotate.add_argument("--source-channel")
    judge_annotate.add_argument("--task-instance-key")
    judge_annotate.add_argument("--instructions")
    judge_annotate.add_argument("--supersedes-artifact-id")
    judge_annotate.add_argument("--timeout-seconds", type=float, default=60.0)
    judge_annotate.add_argument("--dry-run", action="store_true")
    judge_annotate.add_argument("--json", action="store_true")

    judge_override = judge_subparsers.add_parser(
        "override",
        help="Append one manual override annotation for a run",
    )
    judge_override.add_argument("--store", default=DEFAULT_STORE_URI)
    judge_override.add_argument("--session", default="latest")
    judge_override.add_argument("--run-id")
    judge_override.add_argument("--producer", default="human-review")
    judge_override.add_argument("--version")
    judge_override.add_argument("--status", default="active")
    judge_override.add_argument("--payload", default="{}")
    judge_override.add_argument("--review-note")
    judge_override.add_argument("--preserve-review-reasons", action="store_true")
    judge_override.add_argument("--feedback-status", choices=["reviewed", "resolved"])
    judge_override.add_argument("--slice-id")
    judge_override.add_argument("--reviewer")
    judge_override.add_argument("--dry-run", action="store_true")
    judge_override.add_argument("--json", action="store_true")

    artifact = subparsers.add_parser("artifact", help="Append or list artifacts")
    artifact_subparsers = artifact.add_subparsers(dest="artifact_command")
    artifact_append = artifact_subparsers.add_parser("append", help="Append an artifact")
    artifact_append.add_argument("--store", default=DEFAULT_STORE_URI)
    artifact_append.add_argument("--type", required=True, dest="artifact_type")
    artifact_append.add_argument("--target-ref", required=True)
    artifact_append.add_argument("--producer", required=True)
    artifact_append.add_argument("--payload", required=True)
    artifact_append.add_argument("--version")
    artifact_append.add_argument("--session-id")
    artifact_append.add_argument("--run-id")
    artifact_append.add_argument("--session", default="latest")
    artifact_append.add_argument("--status", default="active")
    artifact_append.add_argument("--confidence", type=float)
    artifact_append.add_argument("--supersedes-artifact-id")

    artifact_list = artifact_subparsers.add_parser("list", help="List artifacts")
    artifact_list.add_argument("--store", default=DEFAULT_STORE_URI)
    artifact_list.add_argument("--session", default="latest")
    artifact_list.add_argument("--run-id")
    artifact_list.add_argument("--target-ref")
    artifact_list.add_argument("--type", dest="artifact_type")
    artifact_list.add_argument("--producer")
    artifact_list.add_argument("--version")
    artifact_list.add_argument("--status")
    artifact_list.add_argument("--latest-only", action="store_true")
    artifact_list.add_argument("--json", action="store_true")

    artifact_bootstrap = artifact_subparsers.add_parser(
        "bootstrap",
        help="Derive artifacts from built-in supervision templates",
    )
    artifact_bootstrap.add_argument("--store", default=DEFAULT_STORE_URI)
    artifact_bootstrap.add_argument("--session", default="latest")
    artifact_bootstrap.add_argument("--run-id")
    artifact_bootstrap.add_argument("--template", required=True)
    artifact_bootstrap.add_argument("--producer")
    artifact_bootstrap.add_argument("--version")
    artifact_bootstrap.add_argument("--status", default="active")
    artifact_bootstrap.add_argument("--dry-run", action="store_true")
    artifact_bootstrap.add_argument("--json", action="store_true")

    feedback = subparsers.add_parser("feedback", help="Inspect and sync review queue items")
    feedback_subparsers = feedback.add_subparsers(dest="feedback_command")

    feedback_enqueue = feedback_subparsers.add_parser("enqueue", help="Append one feedback queue item")
    feedback_enqueue.add_argument("--store", default=DEFAULT_STORE_URI)
    feedback_enqueue.add_argument("--slice-id", required=True)
    feedback_enqueue.add_argument("--source", required=True)
    feedback_enqueue.add_argument("--target-ref", required=True)
    feedback_enqueue.add_argument("--reason", required=True)
    feedback_enqueue.add_argument("--payload", default="{}")
    feedback_enqueue.add_argument("--json", action="store_true")

    feedback_list = feedback_subparsers.add_parser("list", help="List feedback queue items")
    feedback_list.add_argument("--store", default=DEFAULT_STORE_URI)
    feedback_list.add_argument("--slice-id")
    feedback_list.add_argument("--status")
    feedback_list.add_argument("--json", action="store_true")

    feedback_sync = feedback_subparsers.add_parser(
        "sync",
        help="Preview or append feedback queue items from a slice review queue",
    )
    feedback_sync.add_argument("--store", default=DEFAULT_STORE_URI)
    feedback_sync.add_argument("--slice-id", required=True)
    feedback_sync.add_argument("--source", default="auto_review")
    feedback_sync.add_argument("--session")
    feedback_sync.add_argument("--run-id")
    feedback_sync.add_argument("--task-instance-key")
    feedback_sync.add_argument("--task-template-hash")
    feedback_sync.add_argument("--min-quality-confidence", type=float)
    feedback_sync.add_argument("--min-verifier-score", type=float)
    feedback_sync.add_argument("--source-channel")
    feedback_sync.add_argument("--limit", type=int)
    feedback_sync.add_argument("--purpose")
    feedback_sync.add_argument("--dry-run", action="store_true")
    feedback_sync.add_argument("--json", action="store_true")

    feedback_resolve = feedback_subparsers.add_parser(
        "resolve",
        help="Mark feedback queue items as reviewed or resolved",
    )
    feedback_resolve.add_argument("--store", default=DEFAULT_STORE_URI)
    feedback_resolve.add_argument("--feedback-id")
    feedback_resolve.add_argument("--slice-id")
    feedback_resolve.add_argument("--target-ref")
    feedback_resolve.add_argument("--from-status")
    feedback_resolve.add_argument("--status", default="resolved")
    feedback_resolve.add_argument("--note")
    feedback_resolve.add_argument("--reviewer")
    feedback_resolve.add_argument("--json", action="store_true")

    eval_parser = subparsers.add_parser("eval", help="Create eval suites and persist evaluation results")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command")

    eval_create_suite = eval_subparsers.add_parser(
        "create-suite",
        help="Create one eval suite from a frozen evaluation cohort",
    )
    eval_create_suite.add_argument("--store", default=DEFAULT_STORE_URI)
    eval_create_suite.add_argument("--slice-id", required=True)
    eval_create_suite.add_argument("--suite-kind", required=True)
    eval_create_suite.add_argument("--cohort-id", required=True)
    eval_create_suite.add_argument("--dataset-snapshot-id")
    eval_create_suite.add_argument("--name")
    eval_create_suite.add_argument("--json", action="store_true")

    eval_scorecard = eval_subparsers.add_parser(
        "record-scorecard",
        help="Record one evaluation scorecard",
    )
    eval_scorecard.add_argument("--store", default=DEFAULT_STORE_URI)
    eval_scorecard.add_argument("--eval-suite-id", required=True)
    eval_scorecard.add_argument("--candidate-model", required=True)
    eval_scorecard.add_argument("--baseline-model", required=True)
    eval_scorecard.add_argument("--metrics", required=True)
    eval_scorecard.add_argument("--thresholds", required=True)
    eval_scorecard.add_argument("--json", action="store_true")

    eval_promotion = eval_subparsers.add_parser(
        "decide-promotion",
        help="Persist one promotion decision from a scorecard",
    )
    eval_promotion.add_argument("--store", default=DEFAULT_STORE_URI)
    eval_promotion.add_argument("--scorecard-id", required=True)
    eval_promotion.add_argument("--stage", required=True)
    eval_promotion.add_argument("--coverage-policy-version", required=True)
    eval_promotion.add_argument("--summary", required=True)
    eval_promotion.add_argument("--rollback-conditions", default="[]")
    eval_promotion.add_argument("--decision")
    eval_promotion.add_argument("--json", action="store_true")

    export = subparsers.add_parser("export", help="Export reusable datasets")
    export_subparsers = export.add_subparsers(dest="export_command")
    dataset = export_subparsers.add_parser("dataset", help="Export a dataset")
    dataset.add_argument("--builder", required=True)
    dataset.add_argument("--session", default="latest")
    dataset.add_argument("--run-id")
    dataset.add_argument("--cohort-id")
    dataset.add_argument("--store", default=DEFAULT_STORE_URI)
    dataset.add_argument("--out", type=Path)
    dataset.add_argument("--dry-run", action="store_true")
    dataset.add_argument("--json", action="store_true")

    readiness = subparsers.add_parser("readiness", help="Inspect dataset export readiness")
    readiness.add_argument("--session", default="latest")
    readiness.add_argument("--run-id")
    readiness.add_argument("--store", default=DEFAULT_STORE_URI)
    readiness.add_argument("--builder")
    readiness.add_argument("--json", action="store_true")

    pipeline = subparsers.add_parser("pipeline", help="Run a capture-to-export workflow")
    pipeline_subparsers = pipeline.add_subparsers(dest="pipeline_command")
    pipeline_run = pipeline_subparsers.add_parser("run", help="Plan or run one export pipeline")
    pipeline_run.add_argument("--session", default="latest")
    pipeline_run.add_argument("--run-id")
    pipeline_run.add_argument("--store", default=DEFAULT_STORE_URI)
    pipeline_run.add_argument("--builder", required=True)
    pipeline_run.add_argument("--template", default="openclaw-defaults")
    pipeline_run.add_argument("--skip-bootstrap", action="store_true")
    pipeline_run.add_argument("--producer")
    pipeline_run.add_argument("--version")
    pipeline_run.add_argument("--artifact-status", default="active")
    pipeline_run.add_argument("--out", type=Path)
    pipeline_run.add_argument("--dry-run", action="store_true")
    pipeline_run.add_argument("--json", action="store_true")

    phase2 = subparsers.add_parser(
        "phase2",
        help="Run the full governance workflow from preparation through export and evaluation",
    )
    phase2_subparsers = phase2.add_subparsers(dest="phase2_command")
    phase2_run = phase2_subparsers.add_parser(
        "run",
        help="Automate prepare, judge, review sync, cohort freeze, export, and optional evaluation",
    )
    phase2_run.add_argument("--store", default=DEFAULT_STORE_URI)
    phase2_run.add_argument("--session", default="latest")
    phase2_run.add_argument("--run-id")
    phase2_run.add_argument("--selection-scope", default="run", choices=["run", "slice"])
    phase2_run.add_argument("--slice-id")
    phase2_run.add_argument("--slice-owner", default="clawgraph.phase2")
    phase2_run.add_argument("--slice-default-use", default="training_candidate")
    phase2_run.add_argument("--slice-risk-level", default="medium")
    phase2_run.add_argument("--prepare-producer", default="clawgraph.prepare")
    phase2_run.add_argument("--prepare-version", default="clawgraph.prepare.v1")
    phase2_run.add_argument("--force-prepare", action="store_true")
    phase2_run.add_argument("--judge-provider", default="heuristic")
    phase2_run.add_argument("--judge-model")
    phase2_run.add_argument("--judge-api-base")
    phase2_run.add_argument("--judge-api-key")
    phase2_run.add_argument("--judge-api-key-env", default="OPENAI_API_KEY")
    phase2_run.add_argument("--judge-producer", default="clawgraph.judge")
    phase2_run.add_argument("--judge-version")
    phase2_run.add_argument("--judge-instructions")
    phase2_run.add_argument("--force-judge", action="store_true")
    phase2_run.add_argument("--builder", dest="builders", action="append")
    phase2_run.add_argument("--output-dir", type=Path)
    phase2_run.add_argument("--cohort-name")
    phase2_run.add_argument("--holdout-fraction", type=float)
    phase2_run.add_argument("--max-members-per-task-instance", type=int, default=1)
    phase2_run.add_argument("--max-members-per-template", type=int)
    phase2_run.add_argument("--min-quality-confidence", type=float)
    phase2_run.add_argument("--min-verifier-score", type=float)
    phase2_run.add_argument("--create-eval-suite", action="store_true")
    phase2_run.add_argument("--suite-kind", default="offline_test")
    phase2_run.add_argument("--eval-cohort-name")
    phase2_run.add_argument("--eval-suite-name")
    phase2_run.add_argument("--scorecard-metrics")
    phase2_run.add_argument("--scorecard-thresholds")
    phase2_run.add_argument("--candidate-model")
    phase2_run.add_argument("--baseline-model")
    phase2_run.add_argument("--promotion-stage")
    phase2_run.add_argument("--coverage-policy-version")
    phase2_run.add_argument("--promotion-summary")
    phase2_run.add_argument("--feedback-source", default="phase2.auto_review")
    phase2_run.add_argument("--dry-run", action="store_true")
    phase2_run.add_argument("--json", action="store_true")

    logits_parser = subparsers.add_parser(
        "logits",
        help="Bridge dataset snapshots to Logits training, evaluation, and router handoff",
    )
    logits_subparsers = logits_parser.add_subparsers(dest="logits_command")

    logits_doctor = logits_subparsers.add_parser(
        "doctor",
        help="Check whether Logits, Cookbook, and required runtime dependencies are importable",
    )
    logits_doctor.add_argument("--json", action="store_true")

    logits_registry = logits_subparsers.add_parser(
        "registry",
        help="Inspect one manifest-backed training registry with lineage across requests, candidates, evals, and handoffs",
    )
    logits_registry.add_argument("--manifest-dir")
    logits_registry.add_argument("--store", default=DEFAULT_STORE_URI)
    logits_registry.add_argument("--json", action="store_true")

    logits_prepare_sft = logits_subparsers.add_parser(
        "prepare-sft",
        help="Adapt one SFT snapshot and emit a Logits training request manifest",
    )
    logits_prepare_sft.add_argument("--store", default=DEFAULT_STORE_URI)
    logits_prepare_sft.add_argument("--dataset-snapshot-id", required=True)
    logits_prepare_sft.add_argument("--output-dir", type=Path, required=True)
    logits_prepare_sft.add_argument("--base-model", required=True)
    logits_prepare_sft.add_argument("--renderer-name")
    logits_prepare_sft.add_argument("--log-path")
    logits_prepare_sft.add_argument("--base-url")
    logits_prepare_sft.add_argument("--api-key-env", default="LOGITS_API_KEY")
    logits_prepare_sft.add_argument("--load-checkpoint-path")
    logits_prepare_sft.add_argument("--learning-rate", type=float, default=2e-4)
    logits_prepare_sft.add_argument("--lr-schedule", default="linear")
    logits_prepare_sft.add_argument("--num-epochs", type=int, default=1)
    logits_prepare_sft.add_argument("--lora-rank", type=int, default=32)
    logits_prepare_sft.add_argument("--batch-size", type=int, default=128)
    logits_prepare_sft.add_argument("--max-length", type=int, default=32768)
    logits_prepare_sft.add_argument("--test-size", type=int, default=0)
    logits_prepare_sft.add_argument("--eval-every", type=int, default=10)
    logits_prepare_sft.add_argument("--save-every", type=int, default=20)
    logits_prepare_sft.add_argument("--ttl-seconds", type=int, default=604800)
    logits_prepare_sft.add_argument("--max-steps", type=int)
    logits_prepare_sft.add_argument("--wandb-project")
    logits_prepare_sft.add_argument("--wandb-name")
    logits_prepare_sft.add_argument("--metadata", default="{}")
    logits_prepare_sft.add_argument("--manifest-out", type=Path)
    logits_prepare_sft.add_argument("--json", action="store_true")

    logits_prepare_dpo = logits_subparsers.add_parser(
        "prepare-dpo",
        help="Adapt one preference snapshot and emit a Logits DPO training request manifest",
    )
    logits_prepare_dpo.add_argument("--store", default=DEFAULT_STORE_URI)
    logits_prepare_dpo.add_argument("--dataset-snapshot-id", required=True)
    logits_prepare_dpo.add_argument("--output-dir", type=Path, required=True)
    logits_prepare_dpo.add_argument("--base-model", required=True)
    logits_prepare_dpo.add_argument("--renderer-name")
    logits_prepare_dpo.add_argument("--log-path")
    logits_prepare_dpo.add_argument("--base-url")
    logits_prepare_dpo.add_argument("--api-key-env", default="LOGITS_API_KEY")
    logits_prepare_dpo.add_argument("--load-checkpoint-path")
    logits_prepare_dpo.add_argument("--learning-rate", type=float, default=1e-5)
    logits_prepare_dpo.add_argument("--lr-schedule", default="linear")
    logits_prepare_dpo.add_argument("--num-epochs", type=int, default=1)
    logits_prepare_dpo.add_argument("--dpo-beta", type=float, default=0.1)
    logits_prepare_dpo.add_argument("--lora-rank", type=int, default=32)
    logits_prepare_dpo.add_argument("--batch-size", type=int, default=256)
    logits_prepare_dpo.add_argument("--max-length", type=int, default=8192)
    logits_prepare_dpo.add_argument("--test-size", type=int, default=0)
    logits_prepare_dpo.add_argument("--eval-every", type=int, default=10)
    logits_prepare_dpo.add_argument("--save-every", type=int, default=20)
    logits_prepare_dpo.add_argument("--ttl-seconds", type=int, default=604800)
    logits_prepare_dpo.add_argument("--max-steps", type=int)
    logits_prepare_dpo.add_argument("--wandb-project")
    logits_prepare_dpo.add_argument("--wandb-name")
    logits_prepare_dpo.add_argument("--metadata", default="{}")
    logits_prepare_dpo.add_argument("--manifest-out", type=Path)
    logits_prepare_dpo.add_argument("--json", action="store_true")

    logits_prepare_rl = logits_subparsers.add_parser(
        "prepare-rl",
        help="Emit a generic environment-driven Logits RL training request manifest",
    )
    logits_prepare_rl.add_argument("--store")
    logits_prepare_rl.add_argument("--output-dir", type=Path, required=True)
    logits_prepare_rl.add_argument("--base-model", required=True)
    logits_prepare_rl.add_argument("--dataset-builder-ref", required=True)
    logits_prepare_rl.add_argument("--dataset-builder-kwargs", default="{}")
    logits_prepare_rl.add_argument("--renderer-name")
    logits_prepare_rl.add_argument("--log-path")
    logits_prepare_rl.add_argument("--base-url")
    logits_prepare_rl.add_argument("--api-key-env", default="LOGITS_API_KEY")
    logits_prepare_rl.add_argument("--load-checkpoint-path")
    logits_prepare_rl.add_argument("--slice-id")
    logits_prepare_rl.add_argument("--eval-suite-id")
    logits_prepare_rl.add_argument("--learning-rate", type=float, default=4e-5)
    logits_prepare_rl.add_argument("--max-tokens", type=int, default=256)
    logits_prepare_rl.add_argument("--lora-rank", type=int, default=32)
    logits_prepare_rl.add_argument("--eval-every", type=int, default=20)
    logits_prepare_rl.add_argument("--save-every", type=int, default=20)
    logits_prepare_rl.add_argument("--max-steps", type=int)
    logits_prepare_rl.add_argument("--metadata", default="{}")
    logits_prepare_rl.add_argument("--manifest-out", type=Path)
    logits_prepare_rl.add_argument("--json", action="store_true")

    logits_submit = logits_subparsers.add_parser(
        "submit",
        help="Submit one Logits training request manifest and emit a candidate manifest",
    )
    logits_submit.add_argument("--store")
    logits_submit.add_argument("--manifest", type=Path, required=True)
    logits_submit.add_argument("--executor-ref")
    logits_submit.add_argument("--candidate-out", type=Path)
    logits_submit.add_argument("--json", action="store_true")

    logits_evaluate = logits_subparsers.add_parser(
        "evaluate",
        help="Run one candidate against a frozen eval suite and write back scorecard/promotion",
    )
    logits_evaluate.add_argument("--store", default=DEFAULT_STORE_URI)
    logits_evaluate.add_argument("--eval-suite-id", required=True)
    logits_evaluate.add_argument("--candidate-manifest", type=Path, required=True)
    logits_evaluate.add_argument("--baseline-model", required=True)
    logits_evaluate.add_argument("--baseline-model-path")
    logits_evaluate.add_argument("--grader", default="exact-match")
    logits_evaluate.add_argument("--grader-ref")
    logits_evaluate.add_argument("--thresholds")
    logits_evaluate.add_argument("--max-tokens", type=int, default=512)
    logits_evaluate.add_argument("--temperature", type=float, default=0.0)
    logits_evaluate.add_argument("--top-p", type=float, default=1.0)
    logits_evaluate.add_argument("--base-url")
    logits_evaluate.add_argument("--scorecard-metadata", default="{}")
    logits_evaluate.add_argument("--record-promotion", action="store_true")
    logits_evaluate.add_argument("--promotion-stage", default="offline")
    logits_evaluate.add_argument("--coverage-policy-version", default="logits.eval.v1")
    logits_evaluate.add_argument("--promotion-summary")
    logits_evaluate.add_argument("--rollback-conditions", default="[]")
    logits_evaluate.add_argument("--output", type=Path)
    logits_evaluate.add_argument("--json", action="store_true")

    logits_handoff = logits_subparsers.add_parser(
        "handoff",
        help="Create one router handoff manifest from a promotion decision and candidate",
    )
    logits_handoff.add_argument("--store", default=DEFAULT_STORE_URI)
    logits_handoff.add_argument("--candidate-manifest", type=Path, required=True)
    logits_handoff.add_argument("--promotion-decision-id", required=True)
    logits_handoff.add_argument("--metadata", default="{}")
    logits_handoff.add_argument("--output", type=Path)
    logits_handoff.add_argument("--json", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "proxy":
        upstream_api_key = args.upstream_api_key or os.getenv("CLAWGRAPH_UPSTREAM_API_KEY")
        run_proxy_server(
            ProxyConfig(
                host=args.host,
                port=args.port,
                store_uri=args.store,
                model_upstream=args.model_upstream,
                tool_upstream=args.tool_upstream,
                upstream_api_key=upstream_api_key,
                auth_token=args.auth_token,
                max_request_body_bytes=args.max_request_body_bytes,
                max_response_body_bytes=args.max_response_body_bytes,
                max_capture_bytes=args.max_capture_bytes,
                max_stream_chunk_facts=args.max_stream_chunk_facts,
                enforce_session_user_binding=not args.disable_session_user_binding,
                payload_dir=args.payload_dir,
            )
        )
        return 0

    if args.command == "control-plane" and args.control_plane_command == "serve":
        auth_token = args.auth_token or os.getenv("CLAWGRAPH_CONTROL_PLANE_TOKEN")
        actor = args.actor or os.getenv("CLAWGRAPH_CONTROL_PLANE_ACTOR", "clawgraph.control_plane")
        run_control_plane_server(
            ControlPlaneConfig(
                host=args.host,
                port=args.port,
                store_uri=args.store,
                manifest_dir=args.manifest_dir or os.getenv("CLAWGRAPH_TRAINING_MANIFEST_DIR"),
                auth_token=auth_token,
                actor=actor,
                session_limit=args.session_limit,
                run_limit=args.run_limit,
                artifact_limit=args.artifact_limit,
            )
        )
        return 0

    if args.command == "payload" and args.payload_command == "read":
        try:
            store = SQLiteFactStore(args.store)
            fact = store.get_fact(args.fact_id)
            if fact is None:
                raise ValueError(f"fact not found: {args.fact_id}")
            body_ref = _body_ref_from_fact_payload(fact.payload)
            if body_ref is None:
                raise ValueError(f"fact does not reference a spilled payload: {args.fact_id}")
            payload_store = LocalPayloadStore(
                root_dir=args.payload_dir,
                store_uri=args.store,
            )
            body = payload_store.read_bytes(body_ref)
            text, parsed = _decode_body_payload(body)
            if args.json:
                payload = {
                    "fact_id": fact.fact_id,
                    "run_id": fact.run_id,
                    "session_id": fact.session_id,
                    "request_id": fact.request_id,
                    "kind": fact.kind,
                    "body_ref": body_ref,
                    "integrity_status": "verified",
                    "text": text,
                }
                if parsed is not None:
                    payload["json"] = parsed
                _print_output(payload)
            else:
                print(text)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "payload" and args.payload_command == "gc":
        try:
            store = SQLiteFactStore(args.store)
            payload_store = LocalPayloadStore(
                root_dir=args.payload_dir,
                store_uri=args.store,
            )
            result = payload_store.garbage_collect(
                referenced_body_refs=(body_ref for _, body_ref in store.iter_fact_body_refs()),
                dry_run=args.dry_run,
                grace_period_seconds=args.grace_seconds,
            )
            _print_output(result if args.json else _render_payload_gc(result))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "bootstrap" and args.bootstrap_command == "openclaw":
        try:
            result = bootstrap_openclaw_session(
                store_uri=args.store,
                session_id=args.session_id,
                run_id=args.run_id,
                user_id=args.user_id,
            )
            _print_output(result.to_dict() if args.json else _render_bootstrap_result(result))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "list" and args.list_command == "sessions":
        store = SQLiteFactStore(args.store)
        sessions = list(store.iter_sessions())
        _print_output(sessions if args.json else _render_session_list(sessions))
        return 0

    if args.command == "list" and args.list_command == "runs":
        try:
            store = SQLiteFactStore(args.store)
            session_id = _resolve_scope_session_id(
                store=store,
                session_value=args.session,
            )
            if session_id is None:
                raise ValueError("no sessions found in store")
            runs = list(store.iter_runs(session_id=session_id))
            _print_output(runs if args.json else _render_run_list(session_id, runs))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "list" and args.list_command == "requests":
        try:
            store = SQLiteFactStore(args.store)
            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
            )
            requests = build_request_span_summaries(facts)
            _print_output(
                [request.to_dict() for request in requests]
                if args.json
                else _render_request_list(session_id, requests)
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "list" and args.list_command == "facts":
        try:
            store = SQLiteFactStore(args.store)
            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
            )
            if args.kind:
                facts = [fact for fact in facts if fact.kind == args.kind]
            if args.actor:
                facts = [fact for fact in facts if fact.actor == args.actor]
            _print_output(
                [
                    {
                        "fact_id": fact.fact_id,
                        "run_id": fact.run_id,
                        "request_id": fact.request_id,
                        "actor": fact.actor,
                        "kind": fact.kind,
                        "timestamp": fact.timestamp.isoformat(),
                    }
                    for fact in facts
                ]
                if args.json
                else _render_fact_list(session_id, facts)
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "list" and args.list_command == "readiness":
        store = SQLiteFactStore(args.store)
        rows = []
        for run_id in list(store.iter_runs())[: args.limit]:
            facts = store.list_facts(run_id=run_id)
            if not facts:
                continue
            session_id = facts[0].session_id
            artifacts = store.list_artifacts(
                session_id=session_id,
                run_id=run_id,
                latest_only=True,
            )
            summary = build_dataset_readiness_summary(
                facts,
                artifacts,
                builder=args.builder,
            )
            rows.append(summary.to_dict())
        _print_output(rows if args.json else _render_readiness_list(rows))
        return 0

    if args.command == "slice" and args.slice_command == "register":
        try:
            metadata = _load_json_argument(args.metadata, label="slice metadata")
            store = SQLiteFactStore(args.store)
            slice_record = new_slice_record(
                slice_id=args.slice_id,
                task_family=args.task_family,
                task_type=args.task_type,
                taxonomy_version=args.taxonomy_version,
                sample_unit=args.sample_unit,
                verifier_contract=args.verifier_contract,
                risk_level=args.risk_level,
                default_use=args.default_use,
                owner=args.owner,
                description=args.description,
                metadata=metadata,
            )
            persisted = store.put_slice(slice_record)
            _print_output(
                persisted.to_dict()
                if args.json
                else _render_slice_record(persisted)
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "slice" and args.slice_command == "list":
        store = SQLiteFactStore(args.store)
        slices = store.list_slices(
            task_family=args.task_family,
            task_type=args.task_type,
            taxonomy_version=args.taxonomy_version,
            default_use=args.default_use,
        )
        _print_output(
            [slice_record.to_dict() for slice_record in slices]
            if args.json
            else _render_slice_list(slices)
        )
        return 0

    if args.command == "slice" and args.slice_command == "candidates":
        try:
            slice_record, candidates = list_slice_candidates(
                store_uri=args.store,
                slice_id=args.slice_id,
                session=args.session,
                run_id=args.run_id,
                task_instance_key=args.task_instance_key,
                task_template_hash=args.task_template_hash,
                min_quality_confidence=args.min_quality_confidence,
                min_verifier_score=args.min_verifier_score,
                source_channel=args.source_channel,
                limit=args.limit,
            )
            payload = {
                "slice": slice_record.to_dict(),
                "candidate_count": len(candidates),
                "candidates": [candidate.to_dict() for candidate in candidates],
            }
            _print_output(payload if args.json else _render_candidate_pool(slice_record, candidates))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "cohort" and args.cohort_command == "freeze":
        try:
            result = freeze_cohort(
                store_uri=args.store,
                slice_id=args.slice_id,
                name=args.name,
                cohort_id=args.cohort_id,
                session=args.session,
                run_id=args.run_id,
                task_instance_key=args.task_instance_key,
                task_template_hash=args.task_template_hash,
                min_quality_confidence=args.min_quality_confidence,
                min_verifier_score=args.min_verifier_score,
                source_channel=args.source_channel,
                limit=args.limit,
            )
            _print_output(
                result.to_dict()
                if args.json
                else _render_cohort_freeze_result(result)
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "cohort" and args.cohort_command == "list":
        store = SQLiteFactStore(args.store)
        cohorts = store.list_cohorts(slice_id=args.slice_id, status=args.status)
        _print_output(
            [cohort.to_dict() for cohort in cohorts]
            if args.json
            else _render_cohort_list(cohorts)
        )
        return 0

    if args.command == "cohort" and args.cohort_command == "show":
        try:
            store = SQLiteFactStore(args.store)
            cohort = store.get_cohort(args.cohort_id)
            if cohort is None:
                raise ValueError(f"cohort not found: {args.cohort_id}")
            members = store.list_cohort_members(args.cohort_id)
            payload = {
                "cohort": cohort.to_dict(),
                "members": [member.to_dict() for member in members],
            }
            _print_output(payload if args.json else _render_cohort_detail(cohort, members))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "replay":
        try:
            store = SQLiteFactStore(args.store)
            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
            )
            artifacts = store.list_artifacts(
                session_id=session_id,
                run_id=args.run_id,
            )
            _print_output(
                {"facts": len(facts), "session_id": session_id, "replay": render_session_replay(facts, artifacts)}
                if args.json
                else render_session_replay(facts, artifacts)
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "branches":
        try:
            store = SQLiteFactStore(args.store)
            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
            )
            artifacts = store.list_artifacts(
                session_id=session_id,
                run_id=args.run_id,
                latest_only=True,
            )
            groups = correlate_request_groups(facts)
            branches, _ = infer_branches(groups, facts=facts)
            _print_output(
                [
                    {
                        "run_id": branch.run_id,
                        "branch_id": branch.branch_id,
                        "branch_type": branch.branch_type,
                        "status": branch.status,
                        "source": branch.source,
                        "parent_branch_id": branch.parent_branch_id,
                        "open_reason": branch.open_reason,
                    }
                    for branch in branches
                ]
                if args.json
                else _render_branch_list(session_id, build_branch_inspect_summaries(facts, artifacts))
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "inspect" and args.inspect_command == "session":
        try:
            store = SQLiteFactStore(args.store)
            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
            )
            artifacts = store.list_artifacts(session_id=session_id, run_id=args.run_id)
            summary = build_session_inspect_summary(facts, artifacts)
            _print_output(summary.to_dict() if args.json else render_session_inspect(summary))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "inspect" and args.inspect_command == "request":
        try:
            store = SQLiteFactStore(args.store)
            session_id = _resolve_scope_session_id(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
            )
            effective_run_id = _resolve_scope_run_id(
                store=store,
                session_value=args.session,
                run_value=args.run_id,
                default_latest_run=False,
            )
            request_id = (
                store.get_latest_request_id(session_id=session_id, run_id=effective_run_id)
                if args.request_id == "latest"
                else args.request_id
            )
            if request_id is None:
                raise ValueError("no requests found in store")
            facts = store.list_facts(
                session_id=session_id,
                request_id=request_id,
                run_id=effective_run_id,
            )
            if not facts:
                raise ValueError(f"request not found: {request_id}")
            artifacts = store.list_artifacts(
                session_id=session_id,
                run_id=effective_run_id,
                latest_only=True,
            )
            summary = get_request_span_summary(facts, request_id, artifacts)
            _print_output(summary.to_dict() if args.json else render_request_inspect(summary))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "inspect" and args.inspect_command == "branch":
        try:
            store = SQLiteFactStore(args.store)
            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
            )
            artifacts = store.list_artifacts(
                session_id=session_id,
                run_id=args.run_id,
                latest_only=True,
            )
            if args.branch_id:
                summary = get_branch_inspect_summary(facts, args.branch_id, artifacts)
                _print_output(summary.to_dict() if args.json else render_branch_inspect(summary))
            else:
                summaries = build_branch_inspect_summaries(facts, artifacts)
                _print_output(
                    [summary.to_dict() for summary in summaries]
                    if args.json
                    else _render_branch_list(session_id, summaries)
                )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "inspect" and args.inspect_command == "workflow":
        try:
            row = inspect_run_workflow(
                store_uri=args.store,
                session=args.session,
                run_id=args.run_id,
                builder=args.builder,
            )
            _print_output(row.to_dict() if args.json else _render_workflow_row(row))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "inspect" and args.inspect_command == "dashboard":
        try:
            if args.iterations is not None and args.iterations <= 0:
                raise ValueError("--iterations must be greater than 0")
            if args.interval_seconds <= 0:
                raise ValueError("--interval-seconds must be greater than 0")
            loop_count = args.iterations if args.watch else 1
            iteration = 0
            while True:
                summary = build_dashboard_snapshot(
                    store_uri=args.store,
                    builder=args.builder,
                    session_limit=args.session_limit,
                    run_limit=args.run_limit,
                )
                if args.watch and not args.json:
                    print("\033[2J\033[H", end="")
                elif args.watch and iteration > 0:
                    _print_output("")
                _print_output(
                    summary.to_dict() if args.json else render_dashboard_snapshot(summary)
                )
                iteration += 1
                if not args.watch:
                    break
                if loop_count is not None and iteration >= loop_count:
                    break
                time.sleep(args.interval_seconds)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "judge" and args.judge_command == "annotate":
        try:
            store = SQLiteFactStore(args.store)
            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
                default_latest_run=True,
            )
            artifacts = store.list_artifacts(
                session_id=session_id,
                run_id=facts[0].run_id,
                latest_only=True,
            )
            plan = plan_judge_annotation(
                facts=facts,
                artifacts=artifacts,
                producer=args.producer or f"clawgraph.judge.{args.provider}",
                provider=args.provider,
                version=args.version,
                status=args.status,
                model=args.model,
                api_base=args.api_base,
                api_key=args.api_key or os.getenv(args.api_key_env),
                instructions=_load_text_argument(args.instructions),
                task_family=args.task_family,
                task_type=args.task_type,
                taxonomy_version=args.taxonomy_version,
                annotation_version=args.annotation_version,
                source_channel=args.source_channel,
                task_instance_key=args.task_instance_key,
                supersedes_artifact_id=args.supersedes_artifact_id,
                timeout_seconds=args.timeout_seconds,
            )
            persisted_artifacts = []
            skipped_count = 0
            if not args.dry_run:
                persisted_artifacts, skipped_count = _persist_unique_artifacts(
                    store=store,
                    session_id=session_id,
                    run_id=facts[0].run_id,
                    artifacts=[plan.artifact],
                )
            payload = {
                **plan.to_dict(),
                "persisted": not args.dry_run and bool(persisted_artifacts),
                "persisted_artifact_id": (
                    persisted_artifacts[0].artifact_id if persisted_artifacts else None
                ),
                "skipped_duplicates": skipped_count,
            }
            _print_output(payload if args.json else _render_judge_plan(payload))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "judge" and args.judge_command == "override":
        try:
            store = SQLiteFactStore(args.store)
            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
                default_latest_run=True,
            )
            artifacts = store.list_artifacts(
                session_id=session_id,
                run_id=facts[0].run_id,
                latest_only=True,
            )
            payload_patch = _load_json_argument(args.payload, label="override payload")
            plan = plan_review_override(
                facts=facts,
                artifacts=artifacts,
                producer=args.producer,
                payload_patch=payload_patch,
                version=args.version,
                status=args.status,
                review_note=_load_text_argument(args.review_note),
                clear_review_reasons=not args.preserve_review_reasons,
            )
            persisted_artifacts = []
            skipped_count = 0
            feedback_updates = []
            if not args.dry_run:
                persisted_artifacts, skipped_count = _persist_unique_artifacts(
                    store=store,
                    session_id=session_id,
                    run_id=facts[0].run_id,
                    artifacts=[plan.artifact],
                )
                if args.feedback_status and persisted_artifacts:
                    feedback_updates = update_feedback_queue_status(
                        store=store,
                        status=args.feedback_status,
                        slice_id=args.slice_id,
                        target_ref=f"run:{facts[0].run_id}",
                        from_status="queued",
                        note=_load_text_argument(args.review_note),
                        reviewer=args.reviewer,
                    )
            payload = {
                **plan.to_dict(),
                "persisted": not args.dry_run and bool(persisted_artifacts),
                "persisted_artifact_id": (
                    persisted_artifacts[0].artifact_id if persisted_artifacts else None
                ),
                "skipped_duplicates": skipped_count,
                "feedback_updates": [item.to_dict() for item in feedback_updates],
            }
            _print_output(payload if args.json else _render_judge_plan(payload))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "artifact" and args.artifact_command == "append":
        try:
            payload = _load_json_argument(args.payload, label="artifact payload")
            store = SQLiteFactStore(args.store)
            target_ref, resolved_session_id = _resolve_target_ref(
                store=store,
                target_ref=args.target_ref,
                session_value=args.session,
                run_value=args.run_id,
            )
            inferred_target_run_id = _infer_run_id_from_target_ref(target_ref)
            session_id = (
                args.session_id
                or resolved_session_id
                or _infer_session_id_from_target_ref(target_ref)
            )
            effective_run_id = (
                args.run_id
                or inferred_target_run_id
                or _resolve_scope_run_id(
                    store=store,
                    session_value=args.session,
                    run_value=args.run_id,
                    default_latest_run=not target_ref.startswith("session:"),
                )
            )
            if session_id is None and effective_run_id is not None:
                session_id = _resolve_session_id_for_run(store=store, run_id=effective_run_id)
            artifact = new_artifact_record(
                artifact_type=args.artifact_type,
                target_ref=target_ref,
                producer=args.producer,
                payload=payload,
                version=args.version,
                session_id=session_id,
                run_id=effective_run_id,
                status=args.status,
                confidence=args.confidence,
                supersedes_artifact_id=args.supersedes_artifact_id,
            )
            store.append_artifact(artifact)
            print(
                f"appended artifact {artifact.artifact_id} "
                f"type={artifact.artifact_type} target={artifact.target_ref}"
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "semantic" and args.semantic_command == "append":
        try:
            payload = _load_json_argument(args.payload, label="semantic payload")
            store = SQLiteFactStore(args.store)
            semantic_fact = new_semantic_event_fact(
                run_id=args.run_id,
                session_id=args.session_id,
                semantic_kind=args.semantic_kind,
                fact_ref=args.fact_ref,
                payload=payload,
                request_id=args.request_id,
                user_id=args.user_id,
                thread_id=args.thread_id,
                task_id=args.task_id,
                branch_id=args.branch_id,
            )
            store.append_fact(semantic_fact)
            print(
                f"appended semantic event {semantic_fact.fact_id} "
                f"kind={args.semantic_kind} session={args.session_id}"
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "feedback" and args.feedback_command == "enqueue":
        try:
            payload = _load_json_argument(args.payload, label="feedback payload")
            feedback = enqueue_feedback(
                store_uri=args.store,
                slice_id=args.slice_id,
                source=args.source,
                target_ref=args.target_ref,
                reason=args.reason,
                payload=payload,
            )
            _print_output(
                feedback.to_dict()
                if args.json
                else f"enqueued feedback {feedback.feedback_id} target={feedback.target_ref}"
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "feedback" and args.feedback_command == "list":
        store = SQLiteFactStore(args.store)
        items = store.list_feedback_queue(slice_id=args.slice_id, status=args.status)
        _print_output(
            [item.to_dict() for item in items]
            if args.json
            else _render_feedback_list(items)
        )
        return 0

    if args.command == "feedback" and args.feedback_command == "sync":
        try:
            if args.dry_run:
                plan = preview_slice_review_queue(
                    store_uri=args.store,
                    slice_id=args.slice_id,
                    session=args.session,
                    run_id=args.run_id,
                    task_instance_key=args.task_instance_key,
                    task_template_hash=args.task_template_hash,
                    min_quality_confidence=args.min_quality_confidence,
                    min_verifier_score=args.min_verifier_score,
                    source_channel=args.source_channel,
                    limit=args.limit,
                    purpose=args.purpose,
                )
                payload = plan.to_dict()
            else:
                result = sync_feedback_queue_from_slice_review(
                    store_uri=args.store,
                    slice_id=args.slice_id,
                    source=args.source,
                    session=args.session,
                    run_id=args.run_id,
                    task_instance_key=args.task_instance_key,
                    task_template_hash=args.task_template_hash,
                    min_quality_confidence=args.min_quality_confidence,
                    min_verifier_score=args.min_verifier_score,
                    source_channel=args.source_channel,
                    limit=args.limit,
                    purpose=args.purpose,
                )
                payload = result.to_dict()
            _print_output(payload if args.json else _render_feedback_sync(payload))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "feedback" and args.feedback_command == "resolve":
        try:
            updated = update_feedback_queue_status(
                store_uri=args.store,
                status=args.status,
                feedback_id=args.feedback_id,
                slice_id=args.slice_id,
                target_ref=args.target_ref,
                from_status=args.from_status,
                note=_load_text_argument(args.note),
                reviewer=args.reviewer,
            )
            payload = {
                "updated_count": len(updated),
                "items": [item.to_dict() for item in updated],
            }
            _print_output(payload if args.json else _render_feedback_resolution(payload))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "artifact" and args.artifact_command == "list":
        try:
            store = SQLiteFactStore(args.store)
            session_id = None
            if args.target_ref is None or args.session != "latest" or args.run_id is not None:
                session_id = _resolve_scope_session_id(
                    store=store,
                    session_value=args.session,
                    run_id=args.run_id,
                )
            artifacts = store.list_artifacts(
                session_id=session_id,
                run_id=args.run_id,
                target_ref=args.target_ref,
                artifact_type=args.artifact_type,
                producer=args.producer,
                version=args.version,
                status=args.status,
                latest_only=args.latest_only,
            )
            if not artifacts:
                print("No artifacts found.")
                return 0
            _print_output(
                [
                    {
                        "artifact_id": artifact.artifact_id,
                        "artifact_type": artifact.artifact_type,
                        "target_ref": artifact.target_ref,
                        "producer": artifact.producer,
                        "version": artifact.version,
                        "status": artifact.status,
                        "confidence": artifact.confidence,
                        "supersedes_artifact_id": artifact.supersedes_artifact_id,
                    }
                    for artifact in artifacts
                ]
                if args.json
                else _render_artifact_list(artifacts)
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "artifact" and args.artifact_command == "bootstrap":
        try:
            store = SQLiteFactStore(args.store)
            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
                default_latest_run=True,
            )
            producer = args.producer or f"clawgraph.{args.template}"
            plan = plan_artifact_bootstrap(
                template=args.template,
                facts=facts,
                producer=producer,
                version=args.version,
                status=args.status,
            )
            persisted_artifacts = list(plan.artifacts)
            skipped_count = 0
            if not args.dry_run:
                persisted_artifacts, skipped_count = _persist_unique_artifacts(
                    store=store,
                    session_id=session_id,
                    run_id=facts[0].run_id,
                    artifacts=plan.artifacts,
                )
            _print_output(
                {
                    **plan.to_dict(),
                    "persisted_count": len(persisted_artifacts) if not args.dry_run else 0,
                    "persisted_artifact_ids": [
                        artifact.artifact_id for artifact in persisted_artifacts
                    ]
                    if not args.dry_run
                    else [],
                    "skipped_duplicates": skipped_count,
                }
                if args.json
                else _render_artifact_bootstrap_plan(
                    plan,
                    persisted=not args.dry_run,
                    persisted_count=len(persisted_artifacts) if not args.dry_run else 0,
                    skipped_count=skipped_count,
                )
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "eval" and args.eval_command == "create-suite":
        try:
            suite = create_eval_suite_from_cohort(
                store_uri=args.store,
                slice_id=args.slice_id,
                suite_kind=args.suite_kind,
                cohort_id=args.cohort_id,
                name=args.name,
                dataset_snapshot_id=args.dataset_snapshot_id,
            )
            _print_output(
                suite.to_dict()
                if args.json
                else f"created eval suite {suite.eval_suite_id} from cohort {suite.cohort_id}"
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "eval" and args.eval_command == "record-scorecard":
        try:
            metrics = _load_json_argument(args.metrics, label="metrics")
            thresholds = _load_json_argument(args.thresholds, label="thresholds")
            scorecard = record_scorecard(
                store_uri=args.store,
                eval_suite_id=args.eval_suite_id,
                candidate_model=args.candidate_model,
                baseline_model=args.baseline_model,
                metrics=metrics,
                thresholds=thresholds,
            )
            _print_output(
                scorecard.to_dict()
                if args.json
                else f"recorded scorecard {scorecard.scorecard_id} verdict={scorecard.verdict}"
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "eval" and args.eval_command == "decide-promotion":
        try:
            rollback_conditions = _load_json_value(
                args.rollback_conditions,
                label="rollback_conditions",
            )
            decision = record_promotion_decision(
                store_uri=args.store,
                scorecard_id=args.scorecard_id,
                stage=args.stage,
                coverage_policy_version=args.coverage_policy_version,
                summary=args.summary,
                rollback_conditions=rollback_conditions
                if isinstance(rollback_conditions, list)
                else list(rollback_conditions.values())
                if isinstance(rollback_conditions, dict)
                else [],
                decision=args.decision,
            )
            _print_output(
                decision.to_dict()
                if args.json
                else f"recorded promotion decision {decision.decision} for scorecard {decision.scorecard_id}"
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "logits" and args.logits_command == "prepare-sft":
        try:
            manifest = prepare_sft_training_request(
                store_uri=args.store,
                dataset_snapshot_id=args.dataset_snapshot_id,
                output_dir=args.output_dir,
                base_model=args.base_model,
                renderer_name=args.renderer_name,
                log_path=args.log_path,
                base_url=args.base_url,
                api_key_env=args.api_key_env,
                load_checkpoint_path=args.load_checkpoint_path,
                learning_rate=args.learning_rate,
                lr_schedule=args.lr_schedule,
                num_epochs=args.num_epochs,
                lora_rank=args.lora_rank,
                batch_size=args.batch_size,
                max_length=args.max_length,
                test_size=args.test_size,
                eval_every=args.eval_every,
                save_every=args.save_every,
                ttl_seconds=args.ttl_seconds,
                max_steps=args.max_steps,
                wandb_project=args.wandb_project,
                wandb_name=args.wandb_name,
                metadata=_load_json_argument(args.metadata, label="metadata"),
                manifest_path=args.manifest_out,
            )
            _print_output(
                manifest.to_dict()
                if args.json
                else _render_training_request_manifest(manifest)
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "logits" and args.logits_command == "doctor":
        payload = describe_logits_runtime()
        _print_output(
            payload
            if args.json
            else "\n".join(
                [
                    "Logits runtime:",
                    (
                        f"workspace_root={payload['workspace_root'] or '<none>'} "
                        f"logits_src={payload['configured_logits_src'] or '<auto>'} "
                        f"cookbook_src={payload['configured_cookbook_src'] or '<auto>'}"
                    ),
                    *[
                        (
                            f"- {module['module']}: "
                            f"{'ok' if module['available'] else 'missing'} "
                            f"({module['location'] or module['error'] or '-'})"
                        )
                        for module in payload["modules"]
                    ],
                ]
            )
        )
        return 0

    if args.command == "logits" and args.logits_command == "registry":
        if not args.manifest_dir and not args.store:
            raise SystemExit("registry requires --store or --manifest-dir")
        payload = build_training_registry(
            manifest_dir=args.manifest_dir,
            store_uri=args.store,
        )
        _print_output(payload if args.json else render_training_registry(payload))
        return 0

    if args.command == "logits" and args.logits_command == "prepare-dpo":
        try:
            manifest = prepare_dpo_training_request(
                store_uri=args.store,
                dataset_snapshot_id=args.dataset_snapshot_id,
                output_dir=args.output_dir,
                base_model=args.base_model,
                renderer_name=args.renderer_name,
                log_path=args.log_path,
                base_url=args.base_url,
                api_key_env=args.api_key_env,
                load_checkpoint_path=args.load_checkpoint_path,
                learning_rate=args.learning_rate,
                lr_schedule=args.lr_schedule,
                num_epochs=args.num_epochs,
                dpo_beta=args.dpo_beta,
                lora_rank=args.lora_rank,
                batch_size=args.batch_size,
                max_length=args.max_length,
                test_size=args.test_size,
                eval_every=args.eval_every,
                save_every=args.save_every,
                ttl_seconds=args.ttl_seconds,
                max_steps=args.max_steps,
                wandb_project=args.wandb_project,
                wandb_name=args.wandb_name,
                metadata=_load_json_argument(args.metadata, label="metadata"),
                manifest_path=args.manifest_out,
            )
            _print_output(
                manifest.to_dict()
                if args.json
                else _render_training_request_manifest(manifest)
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "logits" and args.logits_command == "prepare-rl":
        try:
            manifest = prepare_rl_training_request(
                store_uri=args.store,
                output_dir=args.output_dir,
                base_model=args.base_model,
                dataset_builder_ref=args.dataset_builder_ref,
                dataset_builder_kwargs=_load_json_argument(
                    args.dataset_builder_kwargs,
                    label="dataset_builder_kwargs",
                ),
                renderer_name=args.renderer_name,
                log_path=args.log_path,
                base_url=args.base_url,
                api_key_env=args.api_key_env,
                load_checkpoint_path=args.load_checkpoint_path,
                slice_id=args.slice_id,
                eval_suite_id=args.eval_suite_id,
                learning_rate=args.learning_rate,
                max_tokens=args.max_tokens,
                lora_rank=args.lora_rank,
                eval_every=args.eval_every,
                save_every=args.save_every,
                max_steps=args.max_steps,
                metadata=_load_json_argument(args.metadata, label="metadata"),
                manifest_path=args.manifest_out,
            )
            _print_output(
                manifest.to_dict()
                if args.json
                else _render_training_request_manifest(manifest)
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "logits" and args.logits_command == "submit":
        try:
            loaded_manifest = load_logits_manifest(args.manifest)
            if not isinstance(loaded_manifest, TrainingRequestManifest):
                raise ValueError("submit requires a training request manifest")
            if args.executor_ref:
                loaded_manifest.runtime_config["executor_ref"] = args.executor_ref
            candidate = submit_training_request(
                loaded_manifest,
                store_uri=args.store,
                candidate_path=args.candidate_out,
            )
            _print_output(
                candidate.to_dict()
                if args.json
                else _render_candidate_manifest(candidate)
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "logits" and args.logits_command == "evaluate":
        try:
            loaded_candidate = load_logits_manifest(args.candidate_manifest)
            if not isinstance(loaded_candidate, ModelCandidateManifest):
                raise ValueError("evaluate requires a model candidate manifest")
            thresholds = (
                _load_json_argument(args.thresholds, label="thresholds")
                if args.thresholds
                else None
            )
            rollback_conditions_value = _load_json_value(
                args.rollback_conditions,
                label="rollback_conditions",
            )
            rollback_conditions = (
                rollback_conditions_value if isinstance(rollback_conditions_value, list) else []
            )
            manifest, scorecard, promotion = evaluate_candidate_on_suite(
                store_uri=args.store,
                eval_suite_id=args.eval_suite_id,
                candidate_manifest=loaded_candidate,
                baseline_model=args.baseline_model,
                baseline_model_path=args.baseline_model_path,
                grader_name=args.grader,
                grader_ref=args.grader_ref,
                thresholds=thresholds,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                top_p=args.top_p,
                base_url=args.base_url,
                scorecard_metadata=_load_json_argument(
                    args.scorecard_metadata,
                    label="scorecard_metadata",
                ),
                record_promotion=args.record_promotion,
                promotion_stage=args.promotion_stage,
                coverage_policy_version=args.coverage_policy_version,
                promotion_summary=args.promotion_summary,
                rollback_conditions=rollback_conditions,
                output_path=args.output,
            )
            payload = {
                "eval_execution": manifest.to_dict(),
                "scorecard": scorecard.to_dict(),
                "promotion": None if promotion is None else promotion.to_dict(),
            }
            _print_output(payload if args.json else _render_eval_execution_payload(payload))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "logits" and args.logits_command == "handoff":
        try:
            loaded_candidate = load_logits_manifest(args.candidate_manifest)
            if not isinstance(loaded_candidate, ModelCandidateManifest):
                raise ValueError("handoff requires a model candidate manifest")
            handoff = create_router_handoff_manifest(
                store_uri=args.store,
                candidate_manifest=loaded_candidate,
                promotion_decision_id=args.promotion_decision_id,
                output_path=args.output,
                metadata=_load_json_argument(args.metadata, label="metadata"),
            )
            _print_output(
                handoff.to_dict()
                if args.json
                else _render_router_handoff_manifest(handoff)
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "phase2" and args.phase2_command == "run":
        try:
            judge_api_key = args.judge_api_key or os.getenv(args.judge_api_key_env)
            scorecard_metrics = (
                _load_json_argument(args.scorecard_metrics, label="scorecard_metrics")
                if args.scorecard_metrics
                else None
            )
            scorecard_thresholds = (
                _load_json_argument(args.scorecard_thresholds, label="scorecard_thresholds")
                if args.scorecard_thresholds
                else None
            )
            result = run_phase2_workflow(
                store_uri=args.store,
                session=args.session,
                run_id=args.run_id,
                selection_scope=args.selection_scope,
                slice_id=args.slice_id,
                slice_owner=args.slice_owner,
                slice_default_use=args.slice_default_use,
                slice_risk_level=args.slice_risk_level,
                prepare_producer=args.prepare_producer,
                prepare_version=args.prepare_version,
                force_prepare=args.force_prepare,
                judge_provider=args.judge_provider,
                judge_model=args.judge_model,
                judge_api_base=args.judge_api_base,
                judge_api_key=judge_api_key,
                judge_instructions=args.judge_instructions,
                judge_producer=args.judge_producer,
                judge_version=args.judge_version,
                force_judge=args.force_judge,
                builders=args.builders,
                output_dir=args.output_dir,
                cohort_name=args.cohort_name,
                holdout_fraction=args.holdout_fraction,
                max_members_per_task_instance=args.max_members_per_task_instance,
                max_members_per_template=args.max_members_per_template,
                min_quality_confidence=args.min_quality_confidence,
                min_verifier_score=args.min_verifier_score,
                create_eval_suite=args.create_eval_suite,
                suite_kind=args.suite_kind,
                eval_cohort_name=args.eval_cohort_name,
                eval_suite_name=args.eval_suite_name,
                scorecard_metrics=scorecard_metrics,
                scorecard_thresholds=scorecard_thresholds,
                candidate_model=args.candidate_model,
                baseline_model=args.baseline_model,
                promotion_stage=args.promotion_stage,
                coverage_policy_version=args.coverage_policy_version,
                promotion_summary=args.promotion_summary,
                feedback_source=args.feedback_source,
                dry_run=args.dry_run,
            )
            payload = result.to_dict()
            _print_output(payload if args.json else _render_phase2_run(payload))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "readiness":
        try:
            store = SQLiteFactStore(args.store)
            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
                default_latest_run=True,
            )
            artifacts = store.list_artifacts(
                session_id=session_id,
                run_id=facts[0].run_id,
                latest_only=True,
            )
            summary = build_dataset_readiness_summary(
                facts,
                artifacts,
                builder=args.builder,
            )
            _print_output(summary.to_dict() if args.json else render_dataset_readiness(summary))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "export" and args.export_command == "dataset":
        try:
            plan = plan_dataset_export(
                store_uri=args.store,
                builder=args.builder,
                session=args.session,
                run_id=args.run_id,
                out=args.out,
                cohort_id=args.cohort_id,
            )
            if args.dry_run:
                _print_output(plan.to_dict() if args.json else _render_export_plan(plan))
                return 0
            if args.out is None:
                raise ValueError("--out is required unless --dry-run is set")
            count = export_dataset(
                store_uri=args.store,
                builder=args.builder,
                session=args.session,
                run_id=args.run_id,
                out=args.out,
                cohort_id=args.cohort_id,
            )
            _print_output(
                {
                    "builder": plan.builder,
                    "run_id": plan.run_id,
                    "cohort_id": plan.cohort_id,
                    "dataset_recipe_id": plan.dataset_recipe_id,
                    "dataset_snapshot_id": plan.dataset_snapshot_id,
                    "record_count": count,
                    "output_path": str(args.out),
                    "manifest_path": str(args.out.with_name(f"{args.out.name}.manifest.json")),
                    "ready": plan.ready,
                    "blockers": plan.blockers,
                }
                if args.json
                else f"exported {count} records to {args.out}"
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "pipeline" and args.pipeline_command == "run":
        try:
            store = SQLiteFactStore(args.store)
            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
                default_latest_run=True,
            )
            existing_artifacts = store.list_artifacts(
                session_id=session_id,
                run_id=facts[0].run_id,
                latest_only=True,
            )
            staged_artifacts = []
            skipped_duplicates = 0
            bootstrap_plan = None
            if not args.skip_bootstrap:
                producer = args.producer or f"clawgraph.{args.template}"
                bootstrap_plan = plan_artifact_bootstrap(
                    template=args.template,
                    facts=facts,
                    producer=producer,
                    version=args.version,
                    status=args.artifact_status,
                )
                seen_signatures = {_artifact_signature(artifact) for artifact in existing_artifacts}
                for artifact in bootstrap_plan.artifacts:
                    signature = _artifact_signature(artifact)
                    if signature in seen_signatures:
                        skipped_duplicates += 1
                        continue
                    staged_artifacts.append(artifact)
                    seen_signatures.add(signature)

            combined_artifacts = [*existing_artifacts, *staged_artifacts]
            readiness_summary = build_dataset_readiness_summary(
                facts,
                combined_artifacts,
                builder=args.builder,
            )
            output_path = args.out or _default_export_output_path(
                session_id=session_id,
                builder=args.builder,
                run_id=facts[0].run_id,
            )
            export_plan = plan_dataset_export_for_scope(
                builder=args.builder,
                facts=facts,
                artifacts=combined_artifacts,
                out=output_path,
                run_id=facts[0].run_id,
            )

            persisted_artifacts = []
            exported_count = 0
            exported = False
            manifest_path = output_path.with_name(f"{output_path.name}.manifest.json")
            if not args.dry_run:
                if staged_artifacts:
                    persisted_artifacts, skipped_duplicates = _persist_unique_artifacts(
                        store=store,
                        session_id=session_id,
                        run_id=facts[0].run_id,
                        artifacts=staged_artifacts,
                    )
                if export_plan.ready:
                    exported_count = export_dataset(
                        store_uri=args.store,
                        builder=args.builder,
                        session=session_id,
                        run_id=facts[0].run_id,
                        out=output_path,
                    )
                    exported = True

            payload = {
                "session_id": session_id,
                "run_id": facts[0].run_id,
                "builder": export_plan.builder,
                "template": None if args.skip_bootstrap else args.template,
                "dry_run": args.dry_run,
                "bootstrap": {
                    "planned_count": 0 if bootstrap_plan is None else len(bootstrap_plan.artifacts),
                    "staged_count": len(staged_artifacts),
                    "persisted_count": 0 if args.dry_run else len(persisted_artifacts),
                    "skipped_duplicates": skipped_duplicates,
                    "blockers": [] if bootstrap_plan is None else bootstrap_plan.blockers,
                },
                "readiness": readiness_summary.to_dict(),
                "export": {
                    "ready": export_plan.ready,
                    "record_count": export_plan.record_count,
                    "blockers": export_plan.blockers,
                    "output_path": str(output_path),
                    "manifest_path": str(manifest_path),
                    "exported": exported,
                    "exported_count": exported_count,
                },
            }
            _print_output(payload if args.json else _render_pipeline_run(payload))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    parser.print_help()
    return 0


def _print_output(value: str | dict | list) -> None:
    if isinstance(value, str):
        print(value)
        return
    print(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True))


def _render_branch_list(session_id: str, summaries: list) -> str:
    lines = [f"Session: {session_id}", f"Branches: {len(summaries)}", ""]
    for summary in summaries:
        lines.append(
            f"{summary.branch_id} run={summary.run_id} type={summary.branch_type} source={summary.source} "
            f"status={summary.status} parent={summary.parent_branch_id} "
            f"requests={summary.request_count}"
        )
    return "\n".join(lines)


def _render_artifact_list(artifacts: list) -> str:
    lines = [f"Artifacts: {len(artifacts)}", ""]
    for artifact in artifacts:
        lines.append(
            f"{artifact.artifact_id} {artifact.artifact_type} "
            f"target={artifact.target_ref} producer={artifact.producer} "
            f"status={artifact.status} confidence={artifact.confidence}"
        )
    return "\n".join(lines)


def _render_bootstrap_result(result) -> str:
    return "\n".join(
        [
            f"Seeded session: {result.session_id}",
            f"Run: {result.run_id}",
            f"Request ids: {', '.join(result.request_ids)}",
            f"Response fact: {result.response_fact_id}",
            f"Branch ids: {', '.join(result.branch_ids)}",
            f"Artifact ids: {', '.join(result.artifact_ids)}",
        ]
    )


def _render_session_list(sessions: list[str]) -> str:
    if not sessions:
        return "No sessions found."
    lines = [f"Sessions: {len(sessions)}", ""]
    for session_id in sessions:
        lines.append(session_id)
    return "\n".join(lines)


def _render_run_list(session_id: str, runs: list[str]) -> str:
    if not runs:
        return f"Session: {session_id}\nRuns: 0"
    lines = [f"Session: {session_id}", f"Runs: {len(runs)}", ""]
    lines.extend(runs)
    return "\n".join(lines)


def _render_request_list(session_id: str, requests: list) -> str:
    run_ids = sorted({request.run_id for request in requests})
    lines = [f"Session: {session_id}", f"Runs: {', '.join(run_ids)}", f"Requests: {len(requests)}", ""]
    for request in requests:
        lines.append(
            f"{request.request_id} run={request.run_id} path={request.path} outcome={request.outcome} "
            f"status={request.status_code} branch={request.branch_id}"
        )
    return "\n".join(lines)


def _render_fact_list(session_id: str, facts: list) -> str:
    run_ids = sorted({fact.run_id for fact in facts})
    lines = [f"Session: {session_id}", f"Runs: {', '.join(run_ids)}", f"Facts: {len(facts)}", ""]
    for fact in facts:
        lines.append(
            f"{fact.fact_id} run={fact.run_id} request={fact.request_id} actor={fact.actor} kind={fact.kind}"
        )
    return "\n".join(lines)


def _render_readiness_list(rows: list[dict]) -> str:
    if not rows:
        return "No readiness rows found."
    lines = [f"Runs: {len(rows)}", ""]
    for row in rows:
        builder_text = "; ".join(
            (
                f"{builder['builder']}:ready={builder['ready']},"
                f"records={builder['predicted_records']}"
            )
            for builder in row["builders"]
        )
        lines.append(
            f"{row['session_id']} run={row.get('run_id') or '<multiple>'} "
            f"requests={row['request_spans']} "
            f"artifacts={row['active_artifacts']} {builder_text}"
        )
    return "\n".join(lines)


def _render_slice_record(slice_record) -> str:
    lines = [
        f"Slice: {slice_record.slice_id}",
        f"Family: {slice_record.task_family}",
        f"Type: {slice_record.task_type}",
        f"Taxonomy: {slice_record.taxonomy_version}",
        f"Sample unit: {slice_record.sample_unit}",
        f"Default use: {slice_record.default_use}",
        f"Risk: {slice_record.risk_level}",
        f"Owner: {slice_record.owner}",
        f"Verifier contract: {slice_record.verifier_contract}",
    ]
    if slice_record.description:
        lines.append(f"Description: {slice_record.description}")
    return "\n".join(lines)


def _render_slice_list(slice_records: list) -> str:
    if not slice_records:
        return "No slices found."
    lines = [f"Slices: {len(slice_records)}", ""]
    for slice_record in slice_records:
        lines.append(
            f"{slice_record.slice_id} family={slice_record.task_family} "
            f"type={slice_record.task_type} taxonomy={slice_record.taxonomy_version} "
            f"use={slice_record.default_use}"
        )
    return "\n".join(lines)


def _render_candidate_pool(slice_record, candidates: list) -> str:
    lines = [
        f"Slice: {slice_record.slice_id}",
        f"Candidates: {len(candidates)}",
        "",
    ]
    for candidate in candidates:
        lines.append(
            f"{candidate.run_id} session={candidate.session_id} "
            f"instance={candidate.task_instance_key} template={candidate.task_template_hash} "
            f"quality={candidate.quality_confidence} verifier={candidate.verifier_score} "
            f"source={candidate.source_channel}"
        )
    return "\n".join(lines)


def _render_workflow_row(row) -> str:
    lines = [
        f"Session: {row.session_id}",
        f"Run: {row.run_id}",
        f"Evidence: {row.evidence_level}",
        f"Stage: {row.stage_label} ({row.stage})",
        f"Trajectory: {row.trajectory_status}",
        f"Review: {row.review_status}",
        f"Next action: {row.next_action}",
        f"Ready builders: {', '.join(row.ready_builders) if row.ready_builders else '<none>'}",
    ]
    if row.blockers:
        lines.append("Blockers:")
        lines.extend(f"- {blocker}" for blocker in row.blockers)
    if row.review_reasons:
        lines.append("Review reasons:")
        lines.extend(f"- {reason}" for reason in row.review_reasons)
    return "\n".join(lines)


def _render_judge_plan(payload: dict) -> str:
    artifact = payload["artifact"]
    lines = [
        f"Provider: {payload['provider']}",
        f"Model: {payload['model'] or '<none>'}",
        f"Session: {payload['session_id']}",
        f"Run: {payload['run_id']}",
        f"Persisted: {payload['persisted']}",
        f"Skipped duplicates: {payload['skipped_duplicates']}",
        f"Artifact id: {payload['persisted_artifact_id'] or artifact['artifact_id']}",
        f"Task: {artifact['payload']['task_family']}/{artifact['payload']['task_type']}",
        f"Quality: {artifact['payload']['quality_confidence']}",
        f"Verifier: {artifact['payload']['verifier_score']}",
    ]
    if payload["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in payload["warnings"])
    if payload["review_reasons"]:
        lines.append("Review reasons:")
        lines.extend(f"- {reason}" for reason in payload["review_reasons"])
    feedback_updates = payload.get("feedback_updates") or []
    if feedback_updates:
        lines.append(f"Feedback updated: {len(feedback_updates)}")
    return "\n".join(lines)


def _render_feedback_list(items: list) -> str:
    if not items:
        return "No feedback queue items found."
    lines = [f"Feedback items: {len(items)}", ""]
    for item in items:
        lines.append(
            f"{item.feedback_id} slice={item.slice_id} source={item.source} "
            f"status={item.status} target={item.target_ref} reason={item.reason}"
        )
    return "\n".join(lines)


def _render_feedback_sync(payload: dict) -> str:
    plan = payload["plan"]
    lines = [
        f"Slice: {plan['slice']['slice_id']}",
        f"Purpose: {plan['purpose']}",
        f"Candidates: {plan['candidate_count']}",
        f"Eligible: {plan['eligible_count']}",
        f"Review count: {plan['review_count']}",
    ]
    if "created_count" in payload:
        lines.append(f"Created feedback: {payload['created_count']}")
        lines.append(f"Skipped duplicates: {payload['skipped_duplicates']}")
    if plan["review_queue"]:
        lines.append("Preview:")
        for item in plan["review_queue"][:5]:
            lines.append(
                f"- {item['run_id']} reasons={', '.join(item['reasons'])}"
            )
    return "\n".join(lines)


def _render_feedback_resolution(payload: dict) -> str:
    lines = [f"Updated feedback items: {payload['updated_count']}"]
    for item in payload["items"]:
        lines.append(
            f"- {item['feedback_id']} status={item['status']} target={item['target_ref']}"
        )
    return "\n".join(lines)


def _render_cohort_freeze_result(result) -> str:
    manifest = result.cohort.manifest
    lines = [
        f"Cohort: {result.cohort.cohort_id}",
        f"Name: {result.cohort.name}",
        f"Slice: {result.slice_record.slice_id}",
        f"Members: {len(result.members)}",
        (
            f"Coverage: sessions={manifest['coverage']['session_count']} "
            f"runs={manifest['coverage']['run_count']} "
            f"task_instances={manifest['coverage']['task_instance_count']} "
            f"templates={manifest['coverage']['task_template_count']}"
        ),
        (
            f"Quality: q=[{manifest['quality']['min_quality_confidence']}, "
            f"{manifest['quality']['max_quality_confidence']}] "
            f"verifier=[{manifest['quality']['min_verifier_score']}, "
            f"{manifest['quality']['max_verifier_score']}]"
        ),
    ]
    return "\n".join(lines)


def _render_cohort_list(cohorts: list) -> str:
    if not cohorts:
        return "No cohorts found."
    lines = [f"Cohorts: {len(cohorts)}", ""]
    for cohort in cohorts:
        lines.append(
            f"{cohort.cohort_id} name={cohort.name} status={cohort.status} "
            f"slices={','.join(cohort.slice_ids)} "
            f"runs={cohort.manifest.get('coverage', {}).get('run_count', 0)}"
        )
    return "\n".join(lines)


def _render_cohort_detail(cohort, members: list) -> str:
    lines = [
        f"Cohort: {cohort.cohort_id}",
        f"Name: {cohort.name}",
        f"Status: {cohort.status}",
        f"Slices: {', '.join(cohort.slice_ids)}",
        f"Members: {len(members)}",
        "",
    ]
    for member in members:
        lines.append(
            f"{member.run_id} session={member.session_id} slice={member.slice_id} "
            f"instance={member.task_instance_key} quality={member.quality_confidence} "
            f"verifier={member.verifier_score}"
        )
    return "\n".join(lines)


def _render_export_plan(plan) -> str:
    lines = [
        f"Builder: {plan.builder}",
        f"Session: {plan.session_id}",
        f"Run: {plan.run_id or '<all>'}",
        f"Cohort: {plan.cohort_id or '<none>'}",
        f"Dataset recipe: {plan.dataset_recipe_id}",
        f"Dataset snapshot: {plan.dataset_snapshot_id}",
        f"Ready: {plan.ready}",
        f"Predicted records: {plan.record_count}",
        f"Output path: {plan.output_path or '<not set>'}",
    ]
    if plan.blockers:
        lines.extend(["Blockers:"])
        lines.extend(f"- {blocker}" for blocker in plan.blockers)
    return "\n".join(lines)


def _render_payload_gc(payload: dict) -> str:
    lines = [
        f"Payload root: {payload['root_dir']}",
        f"Managed root: {payload['managed_root']}",
        f"Dry run: {payload['dry_run']}",
        f"Grace seconds: {payload['grace_period_seconds']}",
        f"Referenced files: {payload['referenced_files']}",
        f"Scanned files: {payload['scanned_files']}",
        f"Managed files: {payload['managed_files']}",
        f"Skipped unmanaged files: {payload['skipped_unmanaged_files']}",
        f"Orphan files: {payload['orphan_files']}",
        f"Skipped recent files: {payload['skipped_recent_files']}",
    ]
    if payload["dry_run"]:
        lines.extend(
            [
                f"Would delete files: {payload['would_delete_files']}",
                f"Would delete bytes: {payload['would_delete_bytes']}",
            ]
        )
    else:
        lines.extend(
            [
                f"Deleted files: {payload['deleted_files']}",
                f"Deleted bytes: {payload['deleted_bytes']}",
            ]
        )
    return "\n".join(lines)


def _render_pipeline_run(payload: dict) -> str:
    lines = [
        f"Session: {payload['session_id']}",
        f"Run: {payload['run_id'] or '<all>'}",
        f"Builder: {payload['builder']}",
        f"Dry run: {payload['dry_run']}",
        f"Bootstrap planned: {payload['bootstrap']['planned_count']}",
        f"Bootstrap staged: {payload['bootstrap']['staged_count']}",
        f"Bootstrap persisted: {payload['bootstrap']['persisted_count']}",
        f"Skipped duplicates: {payload['bootstrap']['skipped_duplicates']}",
    ]
    if payload["bootstrap"]["blockers"]:
        lines.append("Bootstrap blockers:")
        lines.extend(f"- {blocker}" for blocker in payload["bootstrap"]["blockers"])
    readiness = payload["readiness"]["builders"][0]
    lines.extend(
        [
            f"Readiness: {readiness['ready']}",
            f"Predicted records: {readiness['predicted_records']}",
        ]
    )
    if readiness["blockers"]:
        lines.append("Readiness blockers:")
        lines.extend(f"- {blocker}" for blocker in readiness["blockers"])
    lines.extend(
        [
            f"Output path: {payload['export']['output_path']}",
            f"Manifest path: {payload['export']['manifest_path']}",
            f"Exported: {payload['export']['exported']}",
            f"Exported count: {payload['export']['exported_count']}",
        ]
    )
    return "\n".join(lines)


def _render_phase2_run(payload: dict) -> str:
    prepare = payload["prepare"]
    lines = [
        f"Session: {payload['session_id']}",
        f"Run: {payload['run_id']}",
        f"Selection scope: {payload['selection_scope']}",
        f"Dry run: {payload['dry_run']}",
        f"Prepare status: {prepare['artifact']['payload'].get('prepare_status', '<unknown>')}",
        f"Workflow: {payload['workflow_before']['stage']} -> {payload['workflow_after']['stage']}",
        f"Next action: {payload['next_action']}",
    ]
    if prepare["blocker_reasons"]:
        lines.append("Preparation blockers:")
        lines.extend(f"- {reason}" for reason in prepare["blocker_reasons"])
    if prepare["review_reasons"]:
        lines.append("Preparation review reasons:")
        lines.extend(f"- {reason}" for reason in prepare["review_reasons"])
    judge = payload.get("judge")
    if judge is not None:
        lines.append(
            "Judge: "
            f"{judge['provider']} persisted={judge['persisted']} "
            f"task={judge['artifact']['payload']['task_family']}/{judge['artifact']['payload']['task_type']}"
        )
    if payload.get("slice") is not None:
        lines.append(
            f"Slice: {payload['slice']['record']['slice_id']} "
            f"created={payload['slice']['created']}"
        )
    feedback_sync = payload.get("feedback_sync")
    if feedback_sync is not None:
        lines.append(
            "Review queue: "
            f"created={feedback_sync.get('created_count', 0)} "
            f"review_count={feedback_sync['plan']['review_count']}"
        )
    if payload["training_cohort"] is not None:
        lines.append(
            f"Training cohort: {payload['training_cohort']['cohort_id']} "
            f"members={payload['training_member_count']}"
        )
    exports = payload.get("exports") or []
    if exports:
        lines.append("Exports:")
        for item in exports:
            lines.append(
                f"- {item['builder']} ready={item['planned']['ready']} "
                f"exported={item['exported']} records={item['record_count']} "
                f"path={item['output_path']}"
            )
    if payload["evaluation_cohort"] is not None:
        lines.append(
            f"Evaluation cohort: {payload['evaluation_cohort']['cohort_id']} "
            f"members={payload['evaluation_member_count']}"
        )
    if payload["eval_suite"] is not None:
        lines.append(
            f"Eval suite: {payload['eval_suite']['eval_suite_id']} "
            f"kind={payload['eval_suite']['suite_kind']}"
        )
    if payload["scorecard"] is not None:
        lines.append(
            f"Scorecard: {payload['scorecard']['scorecard_id']} "
            f"verdict={payload['scorecard']['verdict']}"
        )
    if payload["promotion"] is not None:
        lines.append(
            f"Promotion: {payload['promotion']['promotion_decision_id']} "
            f"decision={payload['promotion']['decision']}"
        )
    if payload["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in payload["warnings"])
    if payload["stopped_reason"]:
        lines.append(f"Stopped at: {payload['stopped_reason']}")
    return "\n".join(lines)


def _render_training_request_manifest(manifest: TrainingRequestManifest) -> str:
    lines = [
        f"Training request: {manifest.training_request_id}",
        f"Recipe: {manifest.recipe_family} ({manifest.recipe_name})",
        f"Base model: {manifest.base_model}",
        f"Dataset snapshot: {manifest.dataset_snapshot_id or '-'}",
        f"Input path: {manifest.input_path or '-'}",
        f"Log path: {manifest.log_path}",
    ]
    return "\n".join(lines)


def _render_candidate_manifest(candidate: ModelCandidateManifest) -> str:
    lines = [
        f"Candidate: {candidate.candidate_model_id}",
        f"Recipe: {candidate.recipe_family} ({candidate.training_recipe})",
        f"Checkpoint path: {candidate.checkpoint_path or '-'}",
        f"Sampler path: {candidate.sampler_path or '-'}",
        f"Log path: {candidate.log_path or '-'}",
    ]
    return "\n".join(lines)


def _render_eval_execution_payload(payload: dict[str, Any]) -> str:
    manifest = payload["eval_execution"]
    scorecard = payload["scorecard"]
    promotion = payload.get("promotion")
    lines = [
        f"Eval execution: {manifest['eval_execution_id']}",
        f"Eval suite: {manifest['eval_suite_id']}",
        f"Candidate model: {manifest['candidate_model_id']}",
        f"Scorecard: {scorecard['scorecard_id']} verdict={scorecard['verdict']}",
    ]
    if promotion is not None:
        lines.append(
            f"Promotion: {promotion['promotion_decision_id']} decision={promotion['decision']}"
        )
    return "\n".join(lines)


def _render_router_handoff_manifest(payload) -> str:
    lines = [
        f"Handoff: {payload.handoff_id}",
        f"Slice: {payload.slice_id}",
        f"Stage: {payload.stage}",
        f"Decision: {payload.decision}",
        f"Candidate model: {payload.candidate_model_id}",
    ]
    return "\n".join(lines)


def _render_artifact_bootstrap_plan(
    plan,
    *,
    persisted: bool,
    persisted_count: int,
    skipped_count: int,
) -> str:
    lines = [
        f"Template: {plan.template}",
        f"Session: {plan.session_id}",
        f"Producer: {plan.producer}",
        f"Ready: {plan.ready}",
        f"Artifacts: {len(plan.artifacts)}",
        f"Persisted: {persisted}",
    ]
    if persisted:
        lines.append(f"Persisted count: {persisted_count}")
        lines.append(f"Skipped duplicates: {skipped_count}")
    if plan.blockers:
        lines.append("Blockers:")
        lines.extend(f"- {blocker}" for blocker in plan.blockers)
    else:
        lines.append("Artifact ids:")
        lines.extend(f"- {artifact.artifact_id}" for artifact in plan.artifacts)
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
