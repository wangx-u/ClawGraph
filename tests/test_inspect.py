from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawgraph.artifacts import E1_ANNOTATION_ARTIFACT_TYPE, E1_ANNOTATION_KIND
from clawgraph.graph import (
    build_branch_inspect_summaries,
    build_request_span_summaries,
    build_session_inspect_summary,
    get_request_span_summary,
    render_branch_inspect,
    render_request_inspect,
    render_session_inspect,
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
                    "capture_truncated": True,
                    "body_ref": {
                        "storage": "local_file",
                        "relative_path": "session_1/run_1/req_1/request_body.json.gz",
                        "content_type": "application/json",
                        "byte_size": 128,
                        "compressed_size": 64,
                    },
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
                    "capture_truncated": True,
                    "body_ref": {
                        "storage": "local_file",
                        "relative_path": "session_1/run_1/req_1/response_body.json.gz",
                        "content_type": "application/json",
                        "byte_size": 512,
                        "compressed_size": 160,
                    },
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
            self.assertEqual(summary.request_payload_spill_count, 1)
            self.assertEqual(summary.response_payload_spill_count, 1)
            self.assertEqual(summary.spilled_payload_bytes, 640)
            self.assertIn("Request payload spills: 1", render_session_inspect(summary))

            request_summary = get_request_span_summary(facts, "req_1")
            self.assertEqual(request_summary.response_body_size, 512)
            self.assertEqual(request_summary.total_latency_ms, 87)
            self.assertEqual(request_summary.upstream_request_id, "up_1")
            self.assertEqual(request_summary.request_payload_spill.fact_id, request.fact_id)
            self.assertEqual(request_summary.response_payload_spill.fact_id, response.fact_id)
            rendered_request = render_request_inspect(request_summary)
            self.assertIn(f"Request payload spill: local_file fact={request.fact_id}", rendered_request)
            self.assertIn(f"Response payload spill: local_file fact={response.fact_id}", rendered_request)

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
            annotation = new_artifact_record(
                artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
                target_ref="run:run_1",
                producer="taxonomy-v1",
                payload={
                    "annotation_kind": E1_ANNOTATION_KIND,
                    "task_family": "captured_agent_task",
                    "task_type": "generic_proxy_capture",
                    "task_template_hash": "tmpl_1",
                    "task_instance_key": "run:run_1",
                    "verifier_name": "judge-v1",
                    "verifier_score": 0.9,
                    "quality_confidence": 0.95,
                    "taxonomy_version": "taxonomy.v1",
                    "annotation_version": "e1.v1",
                    "source_channel": "captured",
                },
                session_id="session_1",
                run_id="run_1",
                confidence=0.95,
            )

            store.append_fact(request)
            store.append_fact(response)
            store.append_artifact(stale_score)
            store.append_artifact(fresh_score)
            store.append_artifact(preference)
            store.append_artifact(annotation)

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
            self.assertEqual(readiness.evidence["level"], "E1")
            self.assertIn(
                "active preference artifacts did not resolve to known branches",
                builders["preference"].blockers,
            )

    def test_request_and_branch_inspect_include_artifact_overlay(self) -> None:
        request = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="model",
            kind="request_started",
            payload={"path": "/v1/chat/completions"},
            request_id="req_1",
        )
        error = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="proxy",
            kind="error_raised",
            payload={"path": "/v1/chat/completions", "status_code": 502},
            request_id="req_1",
            parent_ref=request.fact_id,
        )
        response_score = new_artifact_record(
            artifact_type="score",
            target_ref=f"fact:{error.fact_id}",
            producer="judge-v1",
            payload={"score": 1.0},
            session_id="session_1",
            run_id="run_1",
        )
        branch_preference = new_artifact_record(
            artifact_type="preference",
            target_ref="run:run_1",
            producer="judge-v2",
            payload={"chosen": "br_retry_1", "rejected": "br_main"},
            session_id="session_1",
            run_id="run_1",
        )

        request_summaries = build_request_span_summaries([request, error], [response_score])
        self.assertEqual(request_summaries[0].artifact_count, 1)
        self.assertEqual(request_summaries[0].artifacts[0].artifact_type, "score")
        self.assertIn("Artifact overlay:", render_request_inspect(request_summaries[0]))

        retry_request = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="model",
            kind="request_started",
            payload={"path": "/v1/chat/completions"},
            request_id="req_2",
        )
        retry_response = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="model",
            kind="response_finished",
            payload={"path": "/v1/chat/completions", "status_code": 200},
            request_id="req_2",
            parent_ref=retry_request.fact_id,
        )
        branch_summaries = build_branch_inspect_summaries(
            [request, error, retry_request, retry_response],
            [branch_preference],
        )
        retry_branch = next(summary for summary in branch_summaries if summary.branch_id == "br_retry_1")
        self.assertEqual(retry_branch.artifact_count, 1)
        self.assertEqual(retry_branch.artifacts[0].artifact_type, "preference")
        self.assertIn("Artifact overlay:", render_branch_inspect(retry_branch))

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

    def test_multi_run_session_does_not_infer_cross_run_retry(self) -> None:
        run_1_request = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="model",
            kind="request_started",
            payload={"path": "/v1/chat/completions"},
            request_id="req_run_1",
        )
        run_1_error = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="proxy",
            kind="error_raised",
            payload={"path": "/v1/chat/completions", "status_code": 502},
            request_id="req_run_1",
            parent_ref=run_1_request.fact_id,
        )
        run_2_request = new_fact_event(
            run_id="run_2",
            session_id="session_1",
            actor="model",
            kind="request_started",
            payload={"path": "/v1/chat/completions"},
            request_id="req_run_2",
        )
        run_2_response = new_fact_event(
            run_id="run_2",
            session_id="session_1",
            actor="model",
            kind="response_finished",
            payload={"path": "/v1/chat/completions", "status_code": 200},
            request_id="req_run_2",
            parent_ref=run_2_request.fact_id,
        )

        facts = [run_1_request, run_1_error, run_2_request, run_2_response]
        request_summaries = build_request_span_summaries(facts)
        self.assertEqual(
            [(summary.run_id, summary.branch_id) for summary in request_summaries],
            [("run_1", "br_main"), ("run_2", "br_main")],
        )

        branches = build_branch_inspect_summaries(facts)
        self.assertEqual(
            {(branch.run_id, branch.branch_id, branch.branch_type) for branch in branches},
            {
                ("run_1", "br_main", "mainline"),
                ("run_2", "br_main", "mainline"),
            },
        )


if __name__ == "__main__":
    unittest.main()
