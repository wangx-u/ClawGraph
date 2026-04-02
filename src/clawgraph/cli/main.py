"""CLI entrypoint for ClawGraph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clawgraph.artifacts import plan_artifact_bootstrap
from clawgraph.bootstrap import bootstrap_openclaw_session
from clawgraph.curation import freeze_cohort, list_slice_candidates
from clawgraph.export import (
    build_dataset_readiness_summary,
    export_dataset,
    plan_dataset_export,
    plan_dataset_export_for_scope,
    render_dataset_readiness,
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
    if raw_value.startswith("@"):
        payload_text = Path(raw_value[1:]).read_text(encoding="utf-8")
    else:
        payload_text = raw_value
    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


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
    proxy.add_argument("--max-request-body-bytes", type=int, default=1024 * 1024)
    proxy.add_argument("--max-response-body-bytes", type=int, default=4 * 1024 * 1024)
    proxy.add_argument("--max-capture-bytes", type=int, default=16 * 1024)
    proxy.add_argument("--max-stream-chunk-facts", type=int, default=32)
    proxy.add_argument("--disable-session-user-binding", action="store_true")
    proxy.add_argument("--payload-dir")

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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "proxy":
        run_proxy_server(
            ProxyConfig(
                host=args.host,
                port=args.port,
                store_uri=args.store,
                model_upstream=args.model_upstream,
                tool_upstream=args.tool_upstream,
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
