from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawgraph.graph import (
    build_branch_inspect_summaries,
    build_session_inspect_summary,
    get_request_span_summary,
)
from clawgraph.export import build_dataset_readiness_summary
from clawgraph.protocol.factories import new_artifact_record, new_fact_event
from clawgraph.store import SQLiteFactStore


class InspectViewsTest(unittest.TestCase):
    def test_session_and_request_inspect_views(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/chat/completions",
                    "body_size": 128,
                },
                request_id="req_1",
                user_id="user_1",
            )
            response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={
                    "path": "/v1/chat/completions",
                    "status_code": 200,
                    "body_size": 512,
                    "chunk_count": 3,
                    "total_latency_ms": 87,
                    "ttfb_ms": 19,
                    "stream_duration_ms": 68,
                    "upstream_request_id": "up_1",
                },
                request_id="req_1",
                user_id="user_1",
                parent_ref=request.fact_id,
            )
            artifact = new_artifact_record(
                artifact_type="score",
                target_ref="session:session_1",
                producer="judge-v1",
                payload={"score": 1.0},
                session_id="session_1",
                run_id="run_1",
            )

            store.append_fact(request)
            store.append_fact(response)
            store.append_artifact(artifact)

            facts = store.list_facts("session_1")
            summary = build_session_inspect_summary(
                facts,
                store.list_artifacts(session_id="session_1"),
            )
            self.assertEqual(summary.request_count, 1)
            self.assertEqual(summary.artifact_count, 1)
            self.assertEqual(summary.user_ids, ["user_1"])
            self.assertEqual(summary.avg_latency_ms, 87.0)

            request_summary = get_request_span_summary(facts, "req_1")
            self.assertEqual(request_summary.response_body_size, 512)
            self.assertEqual(request_summary.total_latency_ms, 87)
            self.assertEqual(request_summary.upstream_request_id, "up_1")

    def test_branch_inspect_marks_declared_branch(self) -> None:
        request = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="model",
            kind="request_started",
            payload={"path": "/v1/chat/completions"},
            request_id="req_1",
        )
        semantic = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="runtime",
            kind="semantic_event",
            payload={
                "semantic_kind": "fallback_declared",
                "fact_ref": request.fact_id,
                "payload": {
                    "request_fact_id": request.fact_id,
                    "request_id": "req_1",
                    "branch_id": "br_fallback_declared",
                    "branch_type": "fallback",
                    "status": "failed",
                },
            },
            request_id="req_1",
        )
        response = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="model",
            kind="response_finished",
            payload={"path": "/v1/chat/completions", "status_code": 502},
            request_id="req_1",
            parent_ref=request.fact_id,
        )

        summaries = build_branch_inspect_summaries([request, semantic, response])
        declared = next(summary for summary in summaries if summary.branch_id == "br_fallback_declared")
        self.assertEqual(declared.source, "declared")
        self.assertEqual(declared.branch_type, "fallback")

    def test_artifact_filters_and_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            request = new_fact_event(
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
            response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={
                    "path": "/v1/chat/completions",
                    "status_code": 200,
                    "json": {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
                },
                request_id="req_1",
                parent_ref=request.fact_id,
            )
            stale_score = new_artifact_record(
                artifact_type="score",
                target_ref=f"fact:{response.fact_id}",
                producer="judge-v1",
                payload={"score": 0.2},
                session_id="session_1",
                run_id="run_1",
                status="superseded",
            )
            fresh_score = new_artifact_record(
                artifact_type="score",
                target_ref=f"fact:{response.fact_id}",
                producer="judge-v1",
                payload={"score": 0.9},
                session_id="session_1",
                run_id="run_1",
                confidence=0.95,
                supersedes_artifact_id=stale_score.artifact_id,
            )
            preference = new_artifact_record(
                artifact_type="preference",
                target_ref="branch:br_retry_1",
                producer="judge-v2",
                payload={"chosen": "br_retry_1", "rejected": "br_main"},
                session_id="session_1",
                run_id="run_1",
            )

            store.append_fact(request)
            store.append_fact(response)
            store.append_artifact(stale_score)
            store.append_artifact(fresh_score)
            store.append_artifact(preference)

            active_scores = store.list_artifacts(
                session_id="session_1",
                artifact_type="score",
                status="active",
                latest_only=True,
            )
            self.assertEqual(len(active_scores), 1)
            self.assertEqual(active_scores[0].confidence, 0.95)

            readiness = build_dataset_readiness_summary(
                store.list_facts("session_1"),
                store.list_artifacts(session_id="session_1", latest_only=True),
            )
            builders = {builder.builder: builder for builder in readiness.builders}
            self.assertTrue(builders["sft"].ready)
            self.assertTrue(builders["binary_rl"].ready)
            self.assertFalse(builders["preference"].ready)
            self.assertIn(
                "active preference artifacts did not resolve to known branches",
                builders["preference"].blockers,
            )

    def test_latest_only_keeps_multiple_active_preference_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            first = new_artifact_record(
                artifact_type="preference",
                target_ref="session:session_1",
                producer="judge-v1",
                payload={"chosen": "br_retry_1", "rejected": "br_main"},
                session_id="session_1",
                run_id="run_1",
            )
            second = new_artifact_record(
                artifact_type="preference",
                target_ref="session:session_1",
                producer="judge-v1",
                payload={"chosen": "br_fallback_1", "rejected": "br_main"},
                session_id="session_1",
                run_id="run_1",
            )

            store.append_artifact(first)
            store.append_artifact(second)

            artifacts = store.list_artifacts(session_id="session_1", latest_only=True)
            self.assertEqual(len(artifacts), 2)


if __name__ == "__main__":
    unittest.main()
