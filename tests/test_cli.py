from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawgraph.bootstrap import bootstrap_openclaw_session
from clawgraph.protocol.factories import new_fact_event
from clawgraph.cli.main import _load_json_argument, _resolve_target_ref
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


if __name__ == "__main__":
    unittest.main()
