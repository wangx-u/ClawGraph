from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from clawgraph.bootstrap import bootstrap_openclaw_session
from clawgraph.protocol.factories import new_fact_event
from clawgraph.cli.main import _load_facts_for_scope, _load_json_argument, _resolve_target_ref, main
from clawgraph.proxy.payload_store import LocalPayloadStore
from clawgraph.store import SQLiteFactStore


class CliHelpersTest(unittest.TestCase):
    def test_load_json_argument_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            payload_path = Path(tempdir) / "payload.json"
            payload_path.write_text('{"score": 1}', encoding="utf-8")
            payload = _load_json_argument(f"@{payload_path}", label="artifact payload")
            self.assertEqual(payload["score"], 1)

    def test_resolve_target_ref_shortcuts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            result = bootstrap_openclaw_session(store_uri=store_uri)
            store = SQLiteFactStore(store_uri)

            target_ref, session_id = _resolve_target_ref(
                store=store,
                target_ref="latest-response",
                session_value="latest",
            )
            self.assertEqual(session_id, result.session_id)
            self.assertTrue(target_ref.startswith("fact:"))

            branch_ref, _ = _resolve_target_ref(
                store=store,
                target_ref="latest-succeeded-branch",
                session_value=result.session_id,
            )
            self.assertEqual(branch_ref, "branch:br_retry_declared_1")

            run_ref, run_session_id = _resolve_target_ref(
                store=store,
                target_ref="run:latest",
                session_value=result.session_id,
            )
            self.assertEqual(run_ref, f"run:{result.run_id}")
            self.assertEqual(run_session_id, result.session_id)

    def test_latest_response_prefers_model_over_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)

            model_request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_model",
            )
            model_response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={"path": "/v1/chat/completions", "status_code": 200},
                request_id="req_model",
                parent_ref=model_request.fact_id,
            )
            tool_request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="tool",
                kind="request_started",
                payload={"path": "/tools/run"},
                request_id="req_tool",
            )
            tool_response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="tool",
                kind="response_finished",
                payload={"path": "/tools/run", "status_code": 200},
                request_id="req_tool",
                parent_ref=tool_request.fact_id,
            )

            for fact in (model_request, model_response, tool_request, tool_response):
                store.append_fact(fact)

            target_ref, _ = _resolve_target_ref(
                store=store,
                target_ref="latest-response",
                session_value="session_1",
            )
            self.assertEqual(target_ref, f"fact:{model_response.fact_id}")

            tool_target_ref, _ = _resolve_target_ref(
                store=store,
                target_ref="latest-tool-response",
                session_value="session_1",
            )
            self.assertEqual(tool_target_ref, f"fact:{tool_response.fact_id}")

    def test_load_facts_for_scope_defaults_to_latest_run(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)

            older = new_fact_event(
                run_id="run_older",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_older",
            )
            newer = new_fact_event(
                run_id="run_newer",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_newer",
            )

            store.append_facts([older, newer])

            session_id, facts = _load_facts_for_scope(
                store=store,
                session_value="session_1",
                default_latest_run=True,
            )

            self.assertEqual(session_id, "session_1")
            self.assertEqual([fact.run_id for fact in facts], ["run_newer"])

    def test_list_runs_command_returns_runs_for_latest_session(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)

            store.append_fact(
                new_fact_event(
                    run_id="run_1",
                    session_id="session_1",
                    actor="model",
                    kind="request_started",
                    payload={"path": "/v1/chat/completions"},
                )
            )
            store.append_fact(
                new_fact_event(
                    run_id="run_2",
                    session_id="session_1",
                    actor="model",
                    kind="request_started",
                    payload={"path": "/v1/chat/completions"},
                )
            )

            buffer = StringIO()
            with patch("sys.argv", ["clawgraph", "list", "runs", "--store", store_uri, "--json"]), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            self.assertEqual(json.loads(buffer.getvalue()), ["run_2", "run_1"])

    def test_list_requests_command_defaults_to_session_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)

            store.append_fact(
                new_fact_event(
                    run_id="run_1",
                    session_id="session_1",
                    actor="model",
                    kind="request_started",
                    payload={"path": "/v1/chat/completions"},
                    request_id="req_1",
                )
            )
            store.append_fact(
                new_fact_event(
                    run_id="run_2",
                    session_id="session_1",
                    actor="model",
                    kind="request_started",
                    payload={"path": "/v1/chat/completions"},
                    request_id="req_2",
                )
            )

            buffer = StringIO()
            with patch(
                "sys.argv",
                ["clawgraph", "list", "requests", "--store", store_uri, "--session", "session_1", "--json"],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual({row["run_id"] for row in payload}, {"run_1", "run_2"})

    def test_list_readiness_expands_runs_within_one_session(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)

            request_1 = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/chat/completions",
                    "json": {"messages": [{"role": "user", "content": "hi"}]},
                },
                request_id="req_1",
            )
            response_1 = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={
                    "path": "/v1/chat/completions",
                    "status_code": 200,
                    "json": {"choices": [{"message": {"role": "assistant", "content": "hello"}}]},
                },
                request_id="req_1",
                parent_ref=request_1.fact_id,
            )
            request_2 = new_fact_event(
                run_id="run_2",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/chat/completions",
                    "json": {"messages": [{"role": "user", "content": "bye"}]},
                },
                request_id="req_2",
            )
            response_2 = new_fact_event(
                run_id="run_2",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={
                    "path": "/v1/chat/completions",
                    "status_code": 200,
                    "json": {"choices": [{"message": {"role": "assistant", "content": "goodbye"}}]},
                },
                request_id="req_2",
                parent_ref=request_2.fact_id,
            )
            store.append_facts([request_1, response_1, request_2, response_2])

            buffer = StringIO()
            with patch(
                "sys.argv",
                ["clawgraph", "list", "readiness", "--store", store_uri, "--builder", "sft", "--json"],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(len(payload), 2)
            self.assertEqual({row["run_id"] for row in payload}, {"run_1", "run_2"})

    def test_payload_read_command_returns_spilled_body(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            payload_dir = Path(tempdir) / "payloads"
            store_uri = f"sqlite:///{db_path}"
            store = SQLiteFactStore(store_uri)
            payload_store = LocalPayloadStore(root_dir=payload_dir, store_uri=store_uri)
            body = b'{"hello":"world"}'
            body_ref = payload_store.write_bytes(
                session_id="session_payload",
                run_id="run_payload",
                request_id="req_payload",
                body_kind="response_body",
                request_path="/v1/chat/completions",
                content_type="application/json",
                body=body,
            )
            fact = new_fact_event(
                run_id="run_payload",
                session_id="session_payload",
                actor="model",
                kind="response_finished",
                payload={
                    "path": "/v1/chat/completions",
                    "capture_truncated": True,
                    "body_ref": body_ref,
                },
                request_id="req_payload",
            )
            store.append_fact(fact)

            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "payload",
                    "read",
                    "--store",
                    store_uri,
                    "--payload-dir",
                    str(payload_dir),
                    "--fact-id",
                    fact.fact_id,
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["fact_id"], fact.fact_id)
            self.assertEqual(payload["integrity_status"], "verified")
            self.assertEqual(payload["text"], '{"hello":"world"}')
            self.assertEqual(payload["json"], {"hello": "world"})

    def test_payload_gc_command_removes_orphaned_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            payload_dir = Path(tempdir) / "payloads"
            store_uri = f"sqlite:///{db_path}"
            store = SQLiteFactStore(store_uri)
            payload_store = LocalPayloadStore(root_dir=payload_dir, store_uri=store_uri)

            live_ref = payload_store.write_bytes(
                session_id="session_payload",
                run_id="run_payload",
                request_id="req_live",
                body_kind="response_body",
                request_path="/v1/chat/completions",
                content_type="application/json",
                body=b'{"live":true}',
            )
            orphan_ref = payload_store.write_bytes(
                session_id="session_payload",
                run_id="run_payload",
                request_id="req_orphan",
                body_kind="response_body",
                request_path="/v1/chat/completions",
                content_type="application/json",
                body=b'{"orphan":true}',
            )
            store.append_fact(
                new_fact_event(
                    run_id="run_payload",
                    session_id="session_payload",
                    actor="model",
                    kind="response_finished",
                    payload={
                        "path": "/v1/chat/completions",
                        "capture_truncated": True,
                        "body_ref": live_ref,
                    },
                    request_id="req_live",
                )
            )

            orphan_path = payload_store.resolve_body_path(orphan_ref)
            live_path = payload_store.resolve_body_path(live_ref)
            self.assertTrue(orphan_path.exists())
            self.assertTrue(live_path.exists())

            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "payload",
                    "gc",
                    "--store",
                    store_uri,
                    "--payload-dir",
                    str(payload_dir),
                    "--grace-seconds",
                    "0",
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["referenced_files"], 1)
            self.assertEqual(payload["would_delete_files"], 1)
            self.assertEqual(payload["deleted_files"], 1)
            self.assertFalse(orphan_path.exists())
            self.assertTrue(live_path.exists())


if __name__ == "__main__":
    unittest.main()
