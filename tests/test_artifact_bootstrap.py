from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawgraph.artifacts import plan_artifact_bootstrap
from clawgraph.export import build_dataset_readiness_summary
from clawgraph.protocol.factories import new_fact_event, new_semantic_event_fact
from clawgraph.store import SQLiteFactStore


class ArtifactBootstrapTest(unittest.TestCase):
    def test_openclaw_defaults_bootstrap_makes_session_export_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)

            main_request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_main",
            )
            main_error = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="proxy",
                kind="error_raised",
                payload={"path": "/v1/chat/completions", "status_code": 502},
                request_id="req_main",
                parent_ref=main_request.fact_id,
            )
            retry_request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_retry",
            )
            retry_declared = new_semantic_event_fact(
                run_id="run_1",
                session_id="session_1",
                semantic_kind="retry_declared",
                fact_ref=retry_request.fact_id,
                payload={
                    "request_fact_id": retry_request.fact_id,
                    "request_id": "req_retry",
                    "parent_request_id": "req_main",
                    "branch_id": "br_retry_declared_1",
                    "branch_type": "retry",
                    "status": "succeeded",
                },
                request_id="req_retry",
            )
            retry_response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={"path": "/v1/chat/completions", "status_code": 200},
                request_id="req_retry",
                parent_ref=retry_request.fact_id,
            )

            for fact in (main_request, main_error, retry_request, retry_declared, retry_response):
                store.append_fact(fact)

            plan = plan_artifact_bootstrap(
                template="openclaw-defaults",
                facts=store.list_facts("session_1"),
                producer="clawgraph.quickstart",
                version="v1",
            )
            self.assertTrue(plan.ready)
            self.assertEqual(len(plan.artifacts), 3)
            preference_artifacts = [
                artifact for artifact in plan.artifacts if artifact.artifact_type == "preference"
            ]
            self.assertEqual(len(preference_artifacts), 1)
            self.assertEqual(preference_artifacts[0].target_ref, "run:run_1")

            for artifact in plan.artifacts:
                store.append_artifact(artifact)

            readiness = build_dataset_readiness_summary(
                store.list_facts("session_1"),
                store.list_artifacts(session_id="session_1", latest_only=True),
            )
            builders = {builder.builder: builder for builder in readiness.builders}
            self.assertTrue(builders["binary_rl"].ready)
            self.assertTrue(builders["preference"].ready)


if __name__ == "__main__":
    unittest.main()
