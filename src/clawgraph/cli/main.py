"""CLI entrypoint for ClawGraph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clawgraph.artifacts import plan_artifact_bootstrap
from clawgraph.bootstrap import bootstrap_openclaw_session
from clawgraph.export import (
    build_dataset_readiness_summary,
    export_dataset,
    plan_dataset_export,
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
from clawgraph.protocol.factories import new_artifact_record, new_semantic_event_fact
from clawgraph.proxy import ProxyConfig, run_proxy_server
from clawgraph.store import SQLiteFactStore


DEFAULT_STORE_URI = "sqlite:///clawgraph.db"


def _infer_session_id_from_target_ref(target_ref: str) -> str | None:
    if target_ref.startswith("session:"):
        return target_ref.split(":", 1)[1]
    return None


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

    if target_ref in {"latest-response", "latest-failed-branch", "latest-succeeded-branch"}:
        session_id = _resolve_scope_session_id(
            store=store,
            session_value=session_value,
            run_id=run_value,
        )
        facts = store.list_facts(session_id=session_id, run_id=run_value)
        if not facts:
            raise ValueError("no facts found in scope")
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
    return target_ref, session_value


def _resolve_scope_session_id(
    *,
    store: SQLiteFactStore,
    session_value: str | None,
    run_id: str | None = None,
) -> str | None:
    if session_value not in {None, "latest"}:
        return session_value
    if run_id is not None:
        return None
    return store.get_latest_session_id()


def _load_facts_for_scope(
    *,
    store: SQLiteFactStore,
    session_value: str | None,
    run_id: str | None = None,
) -> tuple[str, list]:
    session_id = _resolve_scope_session_id(
        store=store,
        session_value=session_value,
        run_id=run_id,
    )
    facts = store.list_facts(session_id=session_id, run_id=run_id)
    if not facts:
        raise ValueError("no facts found in scope")
    return facts[0].session_id, facts


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawgraph")
    subparsers = parser.add_subparsers(dest="command")

    proxy = subparsers.add_parser("proxy", help="Start the proxy server")
    proxy.add_argument("--model-upstream")
    proxy.add_argument("--tool-upstream")
    proxy.add_argument("--store", default=DEFAULT_STORE_URI)
    proxy.add_argument("--host", default="127.0.0.1")
    proxy.add_argument("--port", type=int, default=8080)

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

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "proxy":
        run_proxy_server(
            ProxyConfig(
                host=args.host,
                port=args.port,
                store_uri=args.store,
                model_upstream=args.model_upstream,
                tool_upstream=args.tool_upstream,
            )
        )
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

    if args.command == "replay":
        try:
            store = SQLiteFactStore(args.store)
            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value=args.session,
                run_id=args.run_id,
            )
            artifacts = store.list_artifacts(session_id=session_id, run_id=args.run_id)
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
            groups = correlate_request_groups(facts)
            branches, _ = infer_branches(groups, facts=facts)
            _print_output(
                [
                    {
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
                else _render_branch_list(session_id, build_branch_inspect_summaries(facts))
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
            request_id = (
                store.get_latest_request_id(session_id=session_id, run_id=args.run_id)
                if args.request_id == "latest"
                else args.request_id
            )
            if request_id is None:
                raise ValueError("no requests found in store")
            facts = store.list_facts(
                session_id=session_id,
                request_id=request_id,
                run_id=args.run_id,
            )
            if not facts:
                raise ValueError(f"request not found: {request_id}")
            summary = get_request_span_summary(facts, request_id)
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
            if args.branch_id:
                summary = get_branch_inspect_summary(facts, args.branch_id)
                _print_output(summary.to_dict() if args.json else render_branch_inspect(summary))
            else:
                summaries = build_branch_inspect_summaries(facts)
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
            session_id = args.session_id or resolved_session_id or _infer_session_id_from_target_ref(target_ref)
            artifact = new_artifact_record(
                artifact_type=args.artifact_type,
                target_ref=target_ref,
                producer=args.producer,
                payload=payload,
                version=args.version,
                session_id=session_id,
                run_id=args.run_id,
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
                existing_artifacts = store.list_artifacts(
                    session_id=session_id,
                    run_id=args.run_id,
                    latest_only=True,
                )
                seen_signatures = {_artifact_signature(artifact) for artifact in existing_artifacts}
                persisted_artifacts = []
                for artifact in plan.artifacts:
                    signature = _artifact_signature(artifact)
                    if signature in seen_signatures:
                        skipped_count += 1
                        continue
                    store.append_artifact(artifact)
                    persisted_artifacts.append(artifact)
                    seen_signatures.add(signature)
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
            )
            artifacts = store.list_artifacts(
                session_id=session_id,
                run_id=args.run_id,
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
            )
            _print_output(
                {
                    "builder": plan.builder,
                    "run_id": plan.run_id,
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
            f"{summary.branch_id} type={summary.branch_type} source={summary.source} "
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


def _render_request_list(session_id: str, requests: list) -> str:
    lines = [f"Session: {session_id}", f"Requests: {len(requests)}", ""]
    for request in requests:
        lines.append(
            f"{request.request_id} path={request.path} outcome={request.outcome} "
            f"status={request.status_code} branch={request.branch_id}"
        )
    return "\n".join(lines)


def _render_fact_list(session_id: str, facts: list) -> str:
    lines = [f"Session: {session_id}", f"Facts: {len(facts)}", ""]
    for fact in facts:
        lines.append(
            f"{fact.fact_id} request={fact.request_id} actor={fact.actor} kind={fact.kind}"
        )
    return "\n".join(lines)


def _render_export_plan(plan) -> str:
    lines = [
        f"Builder: {plan.builder}",
        f"Session: {plan.session_id}",
        f"Run: {plan.run_id or '<all>'}",
        f"Ready: {plan.ready}",
        f"Predicted records: {plan.record_count}",
        f"Output path: {plan.output_path or '<not set>'}",
    ]
    if plan.blockers:
        lines.extend(["Blockers:"])
        lines.extend(f"- {blocker}" for blocker in plan.blockers)
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
