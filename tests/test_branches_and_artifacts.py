from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawgraph.graph import correlate_request_groups, infer_branches, render_session_replay
from clawgraph.protocol.factories import new_artifact_record, new_fact_event
from clawgraph.store import SQLiteFactStore


class BranchesAndArtifactsTest(unittest.TestCase):
    def test_infer_retry_branch(self) -> None:
        request_1 = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="model",
            kind="request_started",
            payload={"path": "/v1/chat/completions"},
        )
        error_1 = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="proxy",
            kind="error_raised",
            payload={"path": "/v1/chat/completions", "status_code": 502},
            parent_ref=request_1.fact_id,
        )
        request_2 = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="model",
            kind="request_started",
            payload={"path": "/v1/chat/completions"},
        )
        response_2 = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="model",
            kind="response_finished",
            payload={"path": "/v1/chat/completions", "status_code": 200},
            parent_ref=request_2.fact_id,
        )

        groups = correlate_request_groups([request_1, error_1, request_2, response_2])
        branches, request_branch_map = infer_branches(groups)

        self.assertEqual(len(groups), 2)
        self.assertIn("br_main", [branch.branch_id for branch in branches])
        self.assertIn("br_retry_1", [branch.branch_id for branch in branches])
        self.assertEqual(request_branch_map[request_2.fact_id], "br_retry_1")

    def test_artifact_store_and_replay_render(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
            )
            response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={"path": "/v1/chat/completions", "status_code": 200},
                parent_ref=request.fact_id,
            )
            artifact = new_artifact_record(
                artifact_type="score",
                target_ref="session:session_1",
                producer="unit-test",
                payload={"score": 0.8},
                session_id="session_1",
                run_id="run_1",
            )

            store.append_fact(request)
            store.append_fact(response)
            store.append_artifact(artifact)

            artifacts = store.list_artifacts(session_id="session_1")
            self.assertEqual(len(artifacts), 1)
            replay = render_session_replay(store.list_facts("session_1"), artifacts)
            self.assertIn("Artifacts: 1", replay)
            self.assertIn("unit-test", replay)


if __name__ == "__main__":
    unittest.main()
