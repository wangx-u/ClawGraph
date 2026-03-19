"""CLI entrypoint for the early ClawGraph skeleton."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clawgraph.export import (
    build_dataset_readiness_summary,
    export_dataset,
    render_dataset_readiness,
)
from clawgraph.graph import (
    build_branch_inspect_summaries,
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
    replay.add_argument("--store", default=DEFAULT_STORE_URI)
    replay.add_argument("--json", action="store_true")

    branches = subparsers.add_parser("branches", help="Inspect inferred branches")
    branches.add_argument("--session", default="latest")
    branches.add_argument("--store", default=DEFAULT_STORE_URI)
    branches.add_argument("--json", action="store_true")

    inspect = subparsers.add_parser("inspect", help="Inspect operational and learning views")
    inspect_subparsers = inspect.add_subparsers(dest="inspect_command")

    inspect_session = inspect_subparsers.add_parser("session", help="Inspect a session summary")
    inspect_session.add_argument("--session", default="latest")
    inspect_session.add_argument("--store", default=DEFAULT_STORE_URI)
    inspect_session.add_argument("--json", action="store_true")

    inspect_request = inspect_subparsers.add_parser("request", help="Inspect one request span")
    inspect_request.add_argument("--request-id", required=True)
    inspect_request.add_argument("--store", default=DEFAULT_STORE_URI)
    inspect_request.add_argument("--json", action="store_true")

    inspect_branch = inspect_subparsers.add_parser("branch", help="Inspect one branch")
    inspect_branch.add_argument("--session", default="latest")
    inspect_branch.add_argument("--branch-id")
    inspect_branch.add_argument("--store", default=DEFAULT_STORE_URI)
    inspect_branch.add_argument("--json", action="store_true")

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
    artifact_append.add_argument("--status", default="active")
    artifact_append.add_argument("--confidence", type=float)
    artifact_append.add_argument("--supersedes-artifact-id")

    artifact_list = artifact_subparsers.add_parser("list", help="List artifacts")
    artifact_list.add_argument("--store", default=DEFAULT_STORE_URI)
    artifact_list.add_argument("--session", default="latest")
    artifact_list.add_argument("--target-ref")
    artifact_list.add_argument("--type", dest="artifact_type")
    artifact_list.add_argument("--producer")
    artifact_list.add_argument("--version")
    artifact_list.add_argument("--status")
    artifact_list.add_argument("--latest-only", action="store_true")
    artifact_list.add_argument("--json", action="store_true")

    export = subparsers.add_parser("export", help="Export reusable datasets")
    export_subparsers = export.add_subparsers(dest="export_command")
    dataset = export_subparsers.add_parser("dataset", help="Export a dataset")
    dataset.add_argument("--builder", required=True)
    dataset.add_argument("--session", default="latest")
    dataset.add_argument("--store", default=DEFAULT_STORE_URI)
    dataset.add_argument("--out", type=Path, required=True)

    readiness = subparsers.add_parser("readiness", help="Inspect dataset export readiness")
    readiness.add_argument("--session", default="latest")
    readiness.add_argument("--store", default=DEFAULT_STORE_URI)
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

    if args.command == "replay":
        try:
            store = SQLiteFactStore(args.store)
            session_id = (
                store.get_latest_session_id() if args.session == "latest" else args.session
            )
            if session_id is None:
                raise ValueError("no sessions found in store")
            facts = store.list_facts(session_id)
            artifacts = store.list_artifacts(session_id=session_id)
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
            session_id = (
                store.get_latest_session_id() if args.session == "latest" else args.session
            )
            if session_id is None:
                raise ValueError("no sessions found in store")
            facts = store.list_facts(session_id)
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
            session_id = (
                store.get_latest_session_id() if args.session == "latest" else args.session
            )
            if session_id is None:
                raise ValueError("no sessions found in store")
            facts = store.list_facts(session_id)
            artifacts = store.list_artifacts(session_id=session_id)
            summary = build_session_inspect_summary(facts, artifacts)
            _print_output(summary.to_dict() if args.json else render_session_inspect(summary))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "inspect" and args.inspect_command == "request":
        try:
            store = SQLiteFactStore(args.store)
            request_id = (
                store.get_latest_request_id() if args.request_id == "latest" else args.request_id
            )
            if request_id is None:
                raise ValueError("no requests found in store")
            facts = store.list_facts(request_id=request_id)
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
            session_id = (
                store.get_latest_session_id() if args.session == "latest" else args.session
            )
            if session_id is None:
                raise ValueError("no sessions found in store")
            facts = store.list_facts(session_id)
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
            payload = json.loads(args.payload)
            if not isinstance(payload, dict):
                raise ValueError("artifact payload must be a JSON object")
            store = SQLiteFactStore(args.store)
            session_id = args.session_id or _infer_session_id_from_target_ref(args.target_ref)
            artifact = new_artifact_record(
                artifact_type=args.artifact_type,
                target_ref=args.target_ref,
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
            payload = json.loads(args.payload)
            if not isinstance(payload, dict):
                raise ValueError("semantic payload must be a JSON object")
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
            if args.target_ref is None or args.session != "latest":
                session_id = (
                    store.get_latest_session_id() if args.session == "latest" else args.session
                )
            artifacts = store.list_artifacts(
                session_id=session_id,
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

    if args.command == "readiness":
        try:
            store = SQLiteFactStore(args.store)
            session_id = (
                store.get_latest_session_id() if args.session == "latest" else args.session
            )
            if session_id is None:
                raise ValueError("no sessions found in store")
            facts = store.list_facts(session_id)
            artifacts = store.list_artifacts(session_id=session_id, latest_only=True)
            summary = build_dataset_readiness_summary(facts, artifacts)
            _print_output(summary.to_dict() if args.json else render_dataset_readiness(summary))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "export" and args.export_command == "dataset":
        try:
            count = export_dataset(
                store_uri=args.store,
                builder=args.builder,
                session=args.session,
                out=args.out,
            )
            print(f"exported {count} records to {args.out}")
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


if __name__ == "__main__":
    raise SystemExit(main())
