from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawgraph.protocol.factories import new_artifact_record, new_fact_event
from clawgraph.query import ClawGraphQueryService
from clawgraph.store import SQLiteFactStore


class QueryServiceTest(unittest.TestCase):
    def test_load_scope_resolves_explicit_run_to_its_session(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = SQLiteFactStore(f"sqlite:///{Path(tempdir) / 'facts.db'}")
            older = new_fact_event(
                run_id="run_a",
                session_id="sess_a",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_a",
            )
            newer = new_fact_event(
                run_id="run_b",
                session_id="sess_b",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_b",
            )
            store.append_facts([older, newer])

            scope = ClawGraphQueryService(store=store).load_scope(
                session="latest",
                run_id="run_a",
            )

            self.assertEqual(scope.session_id, "sess_a")
            self.assertEqual(scope.run_id, "run_a")
            self.assertEqual([fact.request_id for fact in scope.facts], ["req_a"])

    def test_load_scope_can_include_latest_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = SQLiteFactStore(f"sqlite:///{Path(tempdir) / 'facts.db'}")
            request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_1",
            )
            response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={"path": "/v1/chat/completions", "status_code": 200},
                request_id="req_1",
                parent_ref=request.fact_id,
            )
            stale = new_artifact_record(
                artifact_type="score",
                target_ref=f"fact:{response.fact_id}",
                producer="judge",
                payload={"score": 0.2},
                session_id="session_1",
                run_id="run_1",
                status="superseded",
            )
            fresh = new_artifact_record(
                artifact_type="score",
                target_ref=f"fact:{response.fact_id}",
                producer="judge",
                payload={"score": 0.9},
                session_id="session_1",
                run_id="run_1",
                supersedes_artifact_id=stale.artifact_id,
            )
            store.append_facts([request, response])
            store.append_artifacts([stale, fresh])

            scope = ClawGraphQueryService(store=store).load_scope(
                session="session_1",
                run_id="run_1",
                latest_only_artifacts=True,
            )

            self.assertEqual(len(scope.artifacts), 1)
            self.assertEqual(scope.artifacts[0].artifact_id, fresh.artifact_id)


if __name__ == "__main__":
    unittest.main()
