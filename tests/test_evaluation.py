from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawgraph.artifacts import E1_ANNOTATION_ARTIFACT_TYPE, E1_ANNOTATION_KIND
from clawgraph.curation import freeze_cohort
from clawgraph.evaluation import (
    create_eval_suite_from_cohort,
    enqueue_feedback,
    record_promotion_decision,
    record_scorecard,
)
from clawgraph.export import export_dataset
from clawgraph.protocol.factories import (
    new_artifact_record,
    new_fact_event,
    new_slice_record,
)
from clawgraph.store import SQLiteFactStore


class EvaluationTest(unittest.TestCase):
    def test_eval_suite_scorecard_and_promotion_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = SQLiteFactStore(f"sqlite:///{Path(tempdir) / 'facts.db'}")
            out_path = Path(tempdir) / "train_sft.jsonl"
            store.put_slice(
                new_slice_record(
                    slice_id="slice.capture",
                    task_family="captured_agent_task",
                    task_type="generic_proxy_capture",
                    taxonomy_version="taxonomy.v1",
                    sample_unit="run",
                    verifier_contract="judge-v1",
                    risk_level="medium",
                    default_use="training_candidate",
                    owner="ml-team",
                )
            )
            for run_id, session_id, task_instance_key, template_hash in (
                ("run_1", "session_1", "task-1", "tmpl_1"),
                ("run_2", "session_2", "task-2", "tmpl_2"),
            ):
                request = new_fact_event(
                    run_id=run_id,
                    session_id=session_id,
                    actor="model",
                    kind="request_started",
                    payload={
                        "path": "/v1/chat/completions",
                        "json": {"messages": [{"role": "user", "content": run_id}]},
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
                                {"message": {"role": "assistant", "content": f"ok {run_id}"}}
                            ]
                        },
                    },
                    request_id=f"req_{run_id}",
                    parent_ref=request.fact_id,
                )
                store.append_facts([request, response])
                store.append_artifact(
                    new_artifact_record(
                        artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
                        target_ref=f"run:{run_id}",
                        producer="taxonomy-v1",
                        payload={
                            "annotation_kind": E1_ANNOTATION_KIND,
                            "task_family": "captured_agent_task",
                            "task_type": "generic_proxy_capture",
                            "task_template_hash": template_hash,
                            "task_instance_key": task_instance_key,
                            "verifier_name": "judge-v1",
                            "verifier_score": 0.9,
                            "quality_confidence": 0.95,
                            "taxonomy_version": "taxonomy.v1",
                            "annotation_version": "e1.v1",
                            "source_channel": "captured",
                        },
                        session_id=session_id,
                        run_id=run_id,
                        confidence=0.95,
                    )
                )

            training_cohort = freeze_cohort(
                store=store,
                slice_id="slice.capture",
                name="capture-train",
                run_id="run_1",
            )
            export_dataset(
                store_uri=f"sqlite:///{Path(tempdir) / 'facts.db'}",
                builder="sft",
                cohort_id=training_cohort.cohort.cohort_id,
                out=out_path,
            )
            snapshot = store.list_dataset_snapshots(cohort_id=training_cohort.cohort.cohort_id)[0]
            with self.assertRaises(ValueError):
                create_eval_suite_from_cohort(
                    store=store,
                    slice_id="slice.capture",
                    suite_kind="offline_test",
                    cohort_id=training_cohort.cohort.cohort_id,
                    dataset_snapshot_id=snapshot.dataset_snapshot_id,
                )

            eval_cohort = freeze_cohort(
                store=store,
                slice_id="slice.capture",
                name="capture-holdout",
                run_id="run_2",
                purpose="evaluation",
            )
            suite = create_eval_suite_from_cohort(
                store=store,
                slice_id="slice.capture",
                suite_kind="offline_test",
                cohort_id=eval_cohort.cohort.cohort_id,
                name="capture-offline",
                dataset_snapshot_id=snapshot.dataset_snapshot_id,
            )
            self.assertEqual(suite.manifest["run_count"], 1)

            scorecard = record_scorecard(
                store=store,
                eval_suite_id=suite.eval_suite_id,
                candidate_model="small-v1",
                baseline_model="large-v1",
                metrics={
                    "task_success_rate": 0.96,
                    "verifier_pass_rate": 0.94,
                    "p95_latency": 420,
                },
                thresholds={
                    "task_success_rate": {"op": "gte", "value": 0.95},
                    "verifier_pass_rate": {"op": "gte", "value": 0.90},
                    "p95_latency": {"op": "lte", "value": 500},
                },
            )
            self.assertEqual(scorecard.verdict, "pass")

            decision = record_promotion_decision(
                store=store,
                scorecard_id=scorecard.scorecard_id,
                stage="offline",
                coverage_policy_version="coverage.v1",
                summary="offline suite passed",
                rollback_conditions=["verifier_pass_rate_drop", "fallback_rate_spike"],
            )
            self.assertEqual(decision.decision, "promote")
            self.assertEqual(len(store.list_eval_suites(slice_id="slice.capture")), 1)
            self.assertEqual(len(store.list_scorecards(eval_suite_id=suite.eval_suite_id)), 1)
            self.assertEqual(len(store.list_promotion_decisions(slice_id="slice.capture")), 1)

    def test_feedback_queue_enqueues_items(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = SQLiteFactStore(f"sqlite:///{Path(tempdir) / 'facts.db'}")
            store.put_slice(
                new_slice_record(
                    slice_id="slice.capture",
                    task_family="captured_agent_task",
                    task_type="generic_proxy_capture",
                    taxonomy_version="taxonomy.v1",
                    sample_unit="run",
                    verifier_contract="judge-v1",
                    risk_level="medium",
                    default_use="training_candidate",
                    owner="ml-team",
                )
            )

            feedback = enqueue_feedback(
                store=store,
                slice_id="slice.capture",
                source="shadow_disagreement",
                target_ref="run:run_1",
                reason="candidate disagreed with baseline",
                payload={"candidate_model": "small-v1", "baseline_model": "large-v1"},
            )

            items = store.list_feedback_queue(slice_id="slice.capture")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].feedback_id, feedback.feedback_id)
            self.assertEqual(items[0].status, "queued")


if __name__ == "__main__":
    unittest.main()
