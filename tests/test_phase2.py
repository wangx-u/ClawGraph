from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from clawgraph.artifacts import resolve_e1_annotation_for_run
from clawgraph.cli.main import main
from clawgraph.curation import preview_slice_review_queue
from clawgraph.dashboard import inspect_run_workflow
from clawgraph.judge import plan_judge_annotation
from clawgraph.prepare import plan_prepare_run_artifact
from clawgraph.protocol.factories import new_artifact_record, new_fact_event, new_slice_record
from clawgraph.store import SQLiteFactStore


class _FakeHTTPResponse:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> bytes:
        return self._text.encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class Phase2WorkflowTest(unittest.TestCase):
    def test_openai_compatible_judge_plan_merges_response(self) -> None:
        facts = self._seed_facts()
        response_payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "task_family": "repo_maintenance",
                                "task_type": "bug_fix",
                                "task_instance_key": "issue-123",
                                "task_template_hash": "tmpl_override",
                                "verifier_name": "deepseek-judge",
                                "verifier_score": 0.91,
                                "quality_confidence": 0.88,
                                "taxonomy_version": "taxonomy.v2",
                                "annotation_version": "judge.v2",
                                "source_channel": "captured",
                                "review_reasons": ["novel_path"],
                                "judge_summary": "clear bug-fix trajectory",
                            }
                        )
                    }
                }
            ]
        }
        with patch(
            "clawgraph.judge.urllib.request.urlopen",
            return_value=_FakeHTTPResponse(json.dumps(response_payload)),
        ):
            plan = plan_judge_annotation(
                facts=facts,
                artifacts=[],
                producer="judge.deepseek",
                provider="openai-compatible",
                model="deepseek-chat",
                api_base="https://example.com/v1/chat/completions",
                api_key="sk-test",
            )

        self.assertEqual(plan.artifact.payload["task_family"], "repo_maintenance")
        self.assertEqual(plan.artifact.payload["task_type"], "bug_fix")
        self.assertEqual(plan.artifact.payload["task_instance_key"], "issue-123")
        self.assertEqual(plan.artifact.payload["quality_confidence"], 0.88)
        self.assertEqual(plan.review_reasons, ["novel_path"])

    def test_cli_judge_workflow_and_feedback_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)
            self._append_seed_run(store)
            store.put_slice(
                new_slice_record(
                    slice_id="slice.capture",
                    task_family="captured_agent_task",
                    task_type="generic_proxy_capture",
                    taxonomy_version="clawgraph.bootstrap.v1",
                    sample_unit="run",
                    verifier_contract="heuristic",
                    risk_level="medium",
                    default_use="training_candidate",
                    owner="ml-team",
                )
            )

            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "judge",
                    "annotate",
                    "--store",
                    store_uri,
                    "--session",
                    "session_1",
                    "--run-id",
                    "run_1",
                    "--provider",
                    "heuristic",
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertTrue(payload["persisted"])
            self.assertEqual(payload["artifact"]["payload"]["annotation_kind"], "e1")

            workflow = inspect_run_workflow(
                store_uri=store_uri,
                session="session_1",
                run_id="run_1",
            )
            self.assertEqual(workflow.stage, "review")
            self.assertIn("low_quality_confidence", workflow.review_reasons)

            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "feedback",
                    "sync",
                    "--store",
                    store_uri,
                    "--slice-id",
                    "slice.capture",
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["created_count"], 1)
            self.assertEqual(payload["plan"]["review_count"], 1)

            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "feedback",
                    "sync",
                    "--store",
                    store_uri,
                    "--slice-id",
                    "slice.capture",
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["created_count"], 0)
            self.assertEqual(payload["skipped_duplicates"], 1)

            preview = preview_slice_review_queue(store_uri=store_uri, slice_id="slice.capture")
            self.assertEqual(preview.review_queue[0]["run_id"], "run_1")

            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "feedback",
                    "list",
                    "--store",
                    store_uri,
                    "--slice-id",
                    "slice.capture",
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            items = json.loads(buffer.getvalue())
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["target_ref"], "run:run_1")

            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "judge",
                    "override",
                    "--store",
                    store_uri,
                    "--session",
                    "session_1",
                    "--run-id",
                    "run_1",
                    "--review-note",
                    "human confirmed this sample is reusable",
                    "--feedback-status",
                    "resolved",
                    "--slice-id",
                    "slice.capture",
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertTrue(payload["persisted"])
            self.assertEqual(len(payload["feedback_updates"]), 1)
            self.assertEqual(payload["feedback_updates"][0]["status"], "resolved")

            workflow = inspect_run_workflow(
                store_uri=store_uri,
                session="session_1",
                run_id="run_1",
            )
            self.assertEqual(workflow.stage, "dataset")
            self.assertEqual(workflow.review_status, "human")
            self.assertEqual(workflow.review_reasons, [])

            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "feedback",
                    "resolve",
                    "--store",
                    store_uri,
                    "--target-ref",
                    "run:run_1",
                    "--status",
                    "resolved",
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["updated_count"], 1)
            self.assertEqual(payload["items"][0]["status"], "resolved")

    def test_prepare_plan_detects_secret_like_content(self) -> None:
        request = new_fact_event(
            run_id="run_secret",
            session_id="session_secret",
            actor="model",
            kind="request_started",
            payload={
                "path": "/v1/chat/completions",
                "json": {
                    "messages": [
                        {
                            "role": "user",
                            "content": "use this key sk-1234567890abcdefghijklmnop to continue",
                        }
                    ]
                },
            },
            request_id="req_secret",
        )
        response = new_fact_event(
            run_id="run_secret",
            session_id="session_secret",
            actor="model",
            kind="response_finished",
            payload={
                "path": "/v1/chat/completions",
                "status_code": 200,
                "json": {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
            },
            request_id="req_secret",
            parent_ref=request.fact_id,
        )
        plan = plan_prepare_run_artifact(
            facts=[request, response],
            artifacts=[],
            producer="clawgraph.prepare",
        )

        self.assertEqual(plan.artifact.payload["prepare_status"], "review")
        self.assertIn("secret_like_content_detected", plan.review_reasons)
        self.assertEqual(plan.summary["secret_match_count"], 1)

    def test_resolve_e1_annotation_ignores_non_annotation_artifacts(self) -> None:
        facts = self._seed_facts()
        prepare = plan_prepare_run_artifact(
            facts=facts,
            artifacts=[],
            producer="clawgraph.prepare",
        )

        resolved, artifact_ids = resolve_e1_annotation_for_run(
            session_id="session_1",
            run_id="run_1",
            artifacts=[prepare.artifact],
        )

        self.assertEqual(resolved, {})
        self.assertEqual(artifact_ids, [])

    def test_phase2_cli_can_judge_without_seed_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)
            self._append_seed_run(store, run_id="run_live", session_id="session_live")
            response_payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "task_family": "captured_agent_task",
                                    "task_type": "generic_proxy_capture",
                                    "task_instance_key": "run:run_live",
                                    "task_template_hash": "tmpl-live",
                                    "verifier_name": "deepseek-judge",
                                    "verifier_score": 0.94,
                                    "quality_confidence": 0.91,
                                    "taxonomy_version": "taxonomy.v2",
                                    "annotation_version": "judge.v2",
                                    "source_channel": "captured",
                                    "review_reasons": [],
                                    "judge_summary": "trajectory is reusable for training",
                                }
                            )
                        }
                    }
                ]
            }

            buffer = StringIO()
            with patch(
                "clawgraph.judge.urllib.request.urlopen",
                return_value=_FakeHTTPResponse(json.dumps(response_payload)),
            ), patch(
                "sys.argv",
                [
                    "clawgraph",
                    "phase2",
                    "run",
                    "--store",
                    store_uri,
                    "--session",
                    "session_live",
                    "--run-id",
                    "run_live",
                    "--selection-scope",
                    "run",
                    "--judge-provider",
                    "openai-compatible",
                    "--judge-model",
                    "deepseek-chat",
                    "--judge-api-base",
                    "http://127.0.0.1:8080/v1/chat/completions",
                    "--judge-api-key",
                    "clawgraph-local",
                    "--builder",
                    "sft",
                    "--output-dir",
                    str(Path(tempdir) / "out"),
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["workflow_after"]["stage"], "dataset")
            self.assertEqual(payload["judge"]["provider"], "openai-compatible")
            self.assertTrue(payload["judge"]["persisted"])
            self.assertIsNotNone(payload["slice"])
            self.assertIsNotNone(payload["training_cohort"])
            self.assertEqual(len(payload["exports"]), 1)
            self.assertTrue(payload["exports"][0]["exported"])
            self.assertIsNotNone(payload["exports"][0]["dataset_snapshot"])

    def test_phase2_cli_runs_full_export_and_eval_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)
            self._append_seed_run(store, run_id="run_1", session_id="session_1")
            self._append_seed_run(store, run_id="run_2", session_id="session_2")
            for run_id, session_id, instance_key, template_hash in (
                ("run_1", "session_1", "task-1", "tmpl-1"),
                ("run_2", "session_2", "task-2", "tmpl-2"),
            ):
                store.append_artifact(
                    new_artifact_record(
                        artifact_type="annotation",
                        target_ref=f"run:{run_id}",
                        producer="seed.annotation",
                        session_id=session_id,
                        run_id=run_id,
                        confidence=0.95,
                        payload={
                            "annotation_kind": "e1",
                            "task_family": "captured_agent_task",
                            "task_type": "generic_proxy_capture",
                            "task_template_hash": template_hash,
                            "task_instance_key": instance_key,
                            "verifier_name": "seed-judge",
                            "verifier_score": 0.95,
                            "quality_confidence": 0.95,
                            "taxonomy_version": "taxonomy.v1",
                            "annotation_version": "judge.v1",
                            "source_channel": "captured",
                            "review_reasons": [],
                        },
                    )
                )

            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "phase2",
                    "run",
                    "--store",
                    store_uri,
                    "--session",
                    "session_1",
                    "--run-id",
                    "run_1",
                    "--selection-scope",
                    "slice",
                    "--builder",
                    "sft",
                    "--holdout-fraction",
                    "0.5",
                    "--create-eval-suite",
                    "--suite-kind",
                    "offline_test",
                    "--scorecard-metrics",
                    '{"task_success_rate": 0.96, "verifier_pass_rate": 0.94, "p95_latency": 420}',
                    "--scorecard-thresholds",
                    '{"task_success_rate": {"op": "gte", "value": 0.95}, "verifier_pass_rate": {"op": "gte", "value": 0.9}, "p95_latency": {"op": "lte", "value": 500}}',
                    "--candidate-model",
                    "small-v1",
                    "--baseline-model",
                    "large-v1",
                    "--promotion-stage",
                    "offline",
                    "--coverage-policy-version",
                    "coverage.v1",
                    "--promotion-summary",
                    "phase2 automation passed",
                    "--output-dir",
                    str(Path(tempdir) / "out"),
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["workflow_after"]["stage"], "dataset")
            self.assertTrue(payload["prepare"]["artifact"]["payload"]["prepare_status"] in {"clean", "review"})
            self.assertIsNotNone(payload["slice"])
            self.assertIsNotNone(payload["training_cohort"])
            self.assertEqual(len(payload["exports"]), 1)
            self.assertTrue(payload["exports"][0]["exported"])
            self.assertIsNotNone(payload["exports"][0]["dataset_snapshot"])
            self.assertIsNotNone(payload["evaluation_cohort"])
            self.assertIsNotNone(payload["eval_suite"])
            self.assertIsNotNone(payload["scorecard"])
            self.assertEqual(payload["scorecard"]["verdict"], "pass")
            self.assertIsNotNone(payload["promotion"])
            self.assertEqual(payload["promotion"]["decision"], "promote")

    def test_phase2_cli_auto_derives_scorecard_from_score_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)
            self._append_seed_run(store, run_id="run_1", session_id="session_1")
            self._append_seed_run(store, run_id="run_2", session_id="session_2")
            for run_id, session_id, instance_key, template_hash, score_value in (
                ("run_1", "session_1", "task-1", "tmpl-1", 1.0),
                ("run_2", "session_2", "task-2", "tmpl-2", 1.0),
            ):
                store.append_artifact(
                    new_artifact_record(
                        artifact_type="annotation",
                        target_ref=f"run:{run_id}",
                        producer="seed.annotation",
                        session_id=session_id,
                        run_id=run_id,
                        confidence=0.95,
                        payload={
                            "annotation_kind": "e1",
                            "task_family": "captured_agent_task",
                            "task_type": "generic_proxy_capture",
                            "task_template_hash": template_hash,
                            "task_instance_key": instance_key,
                            "verifier_name": "seed-judge",
                            "verifier_score": 0.95,
                            "quality_confidence": 0.95,
                            "taxonomy_version": "taxonomy.v1",
                            "annotation_version": "judge.v1",
                            "source_channel": "captured",
                            "review_reasons": [],
                        },
                    )
                )
                store.append_artifact(
                    new_artifact_record(
                        artifact_type="score",
                        target_ref=f"run:{run_id}",
                        producer="seed.eval",
                        session_id=session_id,
                        run_id=run_id,
                        confidence=0.95,
                        payload={
                            "score": score_value,
                            "label": score_value >= 1.0,
                            "metric_name": "benchmark_pass",
                        },
                    )
                )

            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "phase2",
                    "run",
                    "--store",
                    store_uri,
                    "--session",
                    "session_1",
                    "--run-id",
                    "run_1",
                    "--selection-scope",
                    "slice",
                    "--builder",
                    "sft",
                    "--holdout-fraction",
                    "0.5",
                    "--create-eval-suite",
                    "--suite-kind",
                    "offline_test",
                    "--output-dir",
                    str(Path(tempdir) / "out"),
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertIsNotNone(payload["eval_suite"])
            self.assertIsNotNone(payload["scorecard"])
            self.assertEqual(payload["scorecard"]["metrics"]["task_success_rate"], 1.0)
            self.assertEqual(payload["scorecard"]["verdict"], "pass")
            self.assertIsNotNone(payload["promotion"])
            self.assertEqual(payload["promotion"]["stage"], "offline")
            self.assertEqual(payload["promotion"]["decision"], "promote")

    @staticmethod
    def _seed_facts() -> list:
        request = new_fact_event(
            run_id="run_1",
            session_id="session_1",
            actor="model",
            kind="request_started",
            payload={
                "path": "/v1/chat/completions",
                "json": {"messages": [{"role": "user", "content": "fix the failing test"}]},
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
                "json": {"choices": [{"message": {"role": "assistant", "content": "working on it"}}]},
            },
            request_id="req_1",
            parent_ref=request.fact_id,
        )
        return [request, response]

    def _append_seed_run(
        self,
        store: SQLiteFactStore,
        *,
        run_id: str = "run_1",
        session_id: str = "session_1",
    ) -> None:
        request = new_fact_event(
            run_id=run_id,
            session_id=session_id,
            actor="model",
            kind="request_started",
            payload={
                "path": "/v1/chat/completions",
                "json": {"messages": [{"role": "user", "content": f"fix task {run_id}"}]},
            },
            request_id=f"req_{run_id}",
        )
        response = new_fact_event(
            run_id=run_id,
            session_id=session_id,
            actor="model",
            kind="response_finished",
            payload={
                "path": "/v1/chat/completions",
                "status_code": 200,
                "json": {
                    "choices": [
                        {"message": {"role": "assistant", "content": f"completed {run_id}"}}
                    ]
                },
            },
            request_id=f"req_{run_id}",
            parent_ref=request.fact_id,
        )
        store.append_facts([request, response])


if __name__ == "__main__":
    unittest.main()
