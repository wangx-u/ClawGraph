from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from clawgraph.artifacts import E1_ANNOTATION_ARTIFACT_TYPE, E1_ANNOTATION_KIND
from clawgraph.cli.main import main
from clawgraph.curation import freeze_cohort
from clawgraph.dashboard import build_dashboard_snapshot, render_dashboard_snapshot
from clawgraph.dashboard_bundle import build_web_dashboard_bundle
from clawgraph.evaluation import (
    create_eval_suite_from_cohort,
    enqueue_feedback,
    record_promotion_decision,
    record_scorecard,
)
from clawgraph.export import export_dataset
from clawgraph.integrations.logits.manifests import (
    EvalExecutionManifest,
    ModelCandidateManifest,
    RouterHandoffManifest,
    TrainingRequestManifest,
    save_manifest,
)
from clawgraph.protocol.factories import (
    new_artifact_record,
    new_fact_event,
    new_semantic_event_fact,
    new_slice_record,
)
from clawgraph.store import SQLiteFactStore


class DashboardSnapshotTest(unittest.TestCase):
    def test_build_dashboard_snapshot_aggregates_execution_and_governance(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = self._seed_dashboard_store(store_uri=store_uri, tempdir=Path(tempdir))

            snapshot = build_dashboard_snapshot(store=store, session_limit=10, run_limit=10)

            self.assertEqual(snapshot.overview.captured_sessions, 2)
            self.assertEqual(snapshot.overview.captured_runs, 3)
            self.assertEqual(snapshot.overview.e1_ready_runs, 2)
            self.assertEqual(snapshot.overview.e2_ready_runs, 1)
            self.assertEqual(snapshot.overview.export_ready_runs, 2)
            self.assertEqual(snapshot.overview.frozen_cohorts, 2)
            self.assertEqual(snapshot.overview.dataset_snapshots, 1)
            self.assertEqual(snapshot.overview.active_eval_suites, 1)
            self.assertEqual(snapshot.overview.scorecards_pass, 1)
            self.assertEqual(snapshot.overview.scorecards_hold, 0)
            self.assertEqual(snapshot.overview.scorecards_fail, 0)
            self.assertEqual(snapshot.overview.feedback_queue_open, 1)
            self.assertEqual(snapshot.workflow_overview.in_progress_runs, 0)
            self.assertEqual(snapshot.workflow_overview.needs_annotation_runs, 1)
            self.assertEqual(snapshot.workflow_overview.needs_review_runs, 0)
            self.assertEqual(snapshot.workflow_overview.ready_for_dataset_runs, 2)
            self.assertEqual(snapshot.workflow_overview.ready_for_eval_runs, 1)
            self.assertEqual(snapshot.workflow_overview.feedback_open_runs, 1)

            session_rows = {row.session_id: row for row in snapshot.recent_sessions}
            self.assertEqual(session_rows["session_1"].run_count, 2)
            self.assertEqual(session_rows["session_1"].e1_ready_runs, 1)
            self.assertEqual(session_rows["session_1"].e2_ready_runs, 1)
            self.assertEqual(session_rows["session_1"].evidence_level, "E0")
            self.assertEqual(session_rows["session_2"].evidence_level, "E1")

            run_rows = {row.run_id: row for row in snapshot.recent_runs}
            self.assertEqual(run_rows["run_1"].evidence_level, "E2")
            self.assertEqual(run_rows["run_1"].task_instance_key, "task-1")
            self.assertIn("sft", run_rows["run_1"].ready_builders)
            self.assertEqual(run_rows["run_3"].evidence_level, "E1")
            self.assertEqual(run_rows["run_2"].ready_builders, [])
            workflow_rows = {row.run_id: row for row in snapshot.workflow_runs}
            self.assertEqual(workflow_rows["run_1"].stage, "evaluate")
            self.assertEqual(workflow_rows["run_2"].stage, "annotate")
            self.assertEqual(workflow_rows["run_3"].stage, "dataset")
            self.assertEqual(workflow_rows["run_2"].review_status, "feedback")

            self.assertEqual(len(snapshot.slices), 1)
            slice_row = snapshot.slices[0]
            self.assertEqual(slice_row.slice_id, "slice.capture")
            self.assertEqual(slice_row.frozen_cohorts, 2)
            self.assertEqual(slice_row.dataset_snapshots, 1)
            self.assertEqual(slice_row.active_eval_suites, 1)
            self.assertEqual(slice_row.latest_scorecard_verdict, "pass")
            self.assertEqual(slice_row.latest_promotion_decision, "promote")
            self.assertEqual(slice_row.feedback_open, 1)

            rendered = render_dashboard_snapshot(snapshot)
            self.assertIn("Overview:", rendered)
            self.assertIn("run_1 session=session_1 level=E2", rendered)
            self.assertIn("slice.capture risk=medium", rendered)

    def test_inspect_dashboard_command_returns_json_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            self._seed_dashboard_store(store_uri=store_uri, tempdir=Path(tempdir))

            buffer = StringIO()
            with patch(
                "sys.argv",
                ["clawgraph", "inspect", "dashboard", "--store", store_uri, "--json"],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            runs = {row["run_id"]: row for row in payload["recent_runs"]}
            self.assertEqual(payload["overview"]["captured_sessions"], 2)
            self.assertEqual(payload["overview"]["e2_ready_runs"], 1)
            self.assertEqual(runs["run_1"]["builder_readiness"]["sft"], True)
            self.assertEqual(payload["slices"][0]["latest_scorecard_verdict"], "pass")

    def test_inspect_dashboard_watch_once_returns_single_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            self._seed_dashboard_store(store_uri=store_uri, tempdir=Path(tempdir))

            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "inspect",
                    "dashboard",
                    "--store",
                    store_uri,
                    "--json",
                    "--watch",
                    "--iterations",
                    "1",
                ],
            ), redirect_stdout(buffer):
                return_code = main()

            self.assertEqual(return_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["overview"]["captured_runs"], 3)

    def test_build_web_dashboard_bundle_aligns_with_snapshot_levels(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = self._seed_dashboard_store(store_uri=store_uri, tempdir=Path(tempdir))
            manifest_dir = Path(tempdir) / "manifests"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            snapshot = store.list_dataset_snapshots()[0]
            suite = store.list_eval_suites()[0]
            scorecard = store.list_scorecards()[0]
            decision = store.list_promotion_decisions()[0]
            request = TrainingRequestManifest(
                recipe_family="sft",
                recipe_name="supervised.chat_sl",
                base_model="meta-llama/Llama-3.2-1B-Instruct",
                dataset_snapshot_id=snapshot.dataset_snapshot_id,
                log_path=str(manifest_dir / "runs" / "capture-sft"),
            )
            candidate = ModelCandidateManifest(
                training_request_id=request.training_request_id,
                recipe_family="sft",
                training_recipe=request.recipe_name,
                base_model=request.base_model,
                dataset_snapshot_id=snapshot.dataset_snapshot_id,
                candidate_model="capture-small-v1",
                checkpoint_path="logits://checkpoint/capture-small-v1",
                sampler_path="logits://sampler/capture-small-v1",
            )
            execution = EvalExecutionManifest(
                eval_suite_id=suite.eval_suite_id,
                candidate_model_id=candidate.candidate_model_id,
                candidate_model=candidate.candidate_model or candidate.candidate_model_id,
                baseline_model="large-v1",
                case_count=1,
                scorecard_id=scorecard.scorecard_id,
                promotion_decision_id=decision.promotion_decision_id,
            )
            handoff = RouterHandoffManifest(
                promotion_decision_id=decision.promotion_decision_id,
                scorecard_id=scorecard.scorecard_id,
                candidate_model_id=candidate.candidate_model_id,
                candidate_model=candidate.candidate_model or candidate.candidate_model_id,
                slice_id="slice.capture",
                stage="offline",
                decision="promote",
                coverage_policy_version="coverage.v1",
            )
            save_manifest(request, manifest_dir / "request.json")
            save_manifest(candidate, manifest_dir / "candidate.json")
            save_manifest(execution, manifest_dir / "execution.json")
            save_manifest(handoff, manifest_dir / "handoff.json")

            bundle = build_web_dashboard_bundle(
                store_uri=store_uri,
                manifest_dir=str(manifest_dir),
                session_limit=10,
                run_limit=10,
            )

            metrics = {item["label"]: item for item in bundle["overviewMetrics"]}
            sessions = {item["id"]: item for item in bundle["sessions"]}
            runs = {
                run["id"]: run
                for session in bundle["sessions"]
                for run in session["runs"]
            }
            readiness = {item["builder"]: item for item in bundle["readinessRows"]}
            workflow_runs = {item["runId"]: item for item in bundle["workflowRuns"]}
            replay_records = {item["runId"]: item for item in bundle["replayRecords"]}

            self.assertEqual(metrics["验证资产"]["value"], "1")
            self.assertEqual(metrics["可导出运行"]["value"], "2")
            self.assertEqual(sessions["session_1"]["evidenceLevel"], "E0")
            self.assertEqual(runs["run_1"]["evidenceLevel"], "E2")
            self.assertEqual(runs["run_3"]["evidenceLevel"], "E1")
            self.assertEqual(runs["run_1"]["stage"], "evaluate")
            self.assertEqual(workflow_runs["run_2"]["reviewStatus"], "feedback")
            self.assertEqual(bundle["ingestSummary"]["needsAnnotationRuns"], 1)
            self.assertEqual(bundle["ingestSummary"]["taskCoverage"], "67%")
            self.assertEqual(bundle["ingestSummary"]["decisionCoverage"], "33%")
            self.assertEqual(bundle["ingestSummary"]["evaluationAssetCount"], 1)
            self.assertTrue(bundle["ingestSummary"]["latestSessionTitle"])
            self.assertIn("到", bundle["snapshots"][0]["timeRangeLabel"])
            self.assertIn("质量", bundle["cohorts"][0]["qualityGateLabel"])
            self.assertTrue(readiness["sft"]["ready"])
            self.assertNotIn("facts", readiness)
            self.assertTrue(runs["run_1"]["title"])
            self.assertTrue(runs["run_1"]["summary"])
            self.assertTrue(all("run_" not in anomaly for anomaly in sessions["session_1"]["anomalies"]))
            self.assertEqual(replay_records["run_1"]["requests"][0]["stepType"], "模型推理")
            self.assertEqual(replay_records["run_1"]["requests"][0]["pathLabel"], "对话推理")
            self.assertTrue(replay_records["run_1"]["requests"][0]["summary"])
            self.assertTrue(replay_records["run_1"]["branches"][0]["title"])
            self.assertTrue(replay_records["run_1"]["branches"][0]["summary"])
            self.assertEqual(bundle["trainingRequests"][0]["recipeFamily"], "sft")
            self.assertEqual(bundle["trainingRequests"][0]["candidateCount"], 1)
            self.assertEqual(bundle["modelCandidates"][0]["candidateModel"], "capture-small-v1")
            self.assertEqual(bundle["modelCandidates"][0]["evalExecutionIds"], [bundle["evalExecutions"][0]["id"]])
            self.assertEqual(bundle["evalExecutions"][0]["evalSuiteId"], suite.eval_suite_id)
            self.assertEqual(bundle["evalExecutions"][0]["scorecardVerdict"], "pass")
            self.assertEqual(bundle["routerHandoffs"][0]["decision"], "promote")
            self.assertEqual(bundle["trainingRegistrySummary"]["requestCount"], 1)
            self.assertIn("verifier_pass_rate_drop", bundle["coverageGuardrails"])

    def test_inferred_only_branching_is_advisory_not_review_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)
            self._append_run(
                store=store,
                session_id="session_adv",
                run_id="run_adv",
                prompt="fix benchmark issue",
                response_text="submitted patch",
                task_instance_key="sqlfluff__sqlfluff-1625",
                template_hash="tmpl_adv",
                with_annotation=True,
            )
            store.append_artifact(
                new_artifact_record(
                    artifact_type="workflow_report",
                    target_ref="run:run_adv",
                    producer="clawgraph.prepare",
                    session_id="session_adv",
                    run_id="run_adv",
                    confidence=0.7,
                    payload={
                        "annotation_kind": "trajectory_prepare",
                        "prepare_version": "clawgraph.prepare.v1",
                        "prepare_status": "review",
                        "blocker_reasons": [],
                        "review_reasons": ["inferred_only_branching"],
                        "request_count": 1,
                        "success_count": 1,
                        "failure_count": 0,
                        "open_count": 0,
                        "branch_count": 2,
                        "declared_branch_count": 0,
                        "declared_branch_ratio": 0.0,
                        "prompt_request_count": 1,
                        "assistant_response_count": 1,
                        "secret_matches": {},
                        "secret_match_count": 0,
                        "request_samples": ["benchmark prompt"],
                        "response_samples": ["benchmark response"],
                    },
                )
            )

            snapshot = build_dashboard_snapshot(store=store, session_limit=10, run_limit=10)
            workflow_rows = {row.run_id: row for row in snapshot.workflow_runs}
            row = workflow_rows["run_adv"]

            self.assertEqual(row.stage, "dataset")
            self.assertEqual(row.review_status, "clean")
            self.assertIn("inferred_only_branching", row.review_reasons)
            self.assertIn("关键分支仍主要依赖推断恢复", row.blockers)

    def _seed_dashboard_store(self, *, store_uri: str, tempdir: Path) -> SQLiteFactStore:
        store = SQLiteFactStore(store_uri)
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

        self._append_run(
            store=store,
            session_id="session_1",
            run_id="run_1",
            prompt="fix bug one",
            response_text="patched run 1",
            task_instance_key="task-1",
            template_hash="tmpl_1",
            with_annotation=True,
            semantic_kinds=["route_decided", "task_completed"],
        )
        self._append_run(
            store=store,
            session_id="session_1",
            run_id="run_2",
            prompt="fix bug two",
            response_text="patched run 2",
            task_instance_key="task-2",
            template_hash="tmpl_2",
            with_annotation=False,
        )
        self._append_run(
            store=store,
            session_id="session_2",
            run_id="run_3",
            prompt="fix bug three",
            response_text="patched run 3",
            task_instance_key="task-3",
            template_hash="tmpl_3",
            with_annotation=True,
        )

        training = freeze_cohort(
            store=store,
            slice_id="slice.capture",
            name="capture-train",
            run_id="run_1",
        )
        out_path = tempdir / "capture-train.sft.jsonl"
        export_dataset(
            store_uri=store_uri,
            builder="sft",
            cohort_id=training.cohort.cohort_id,
            out=out_path,
        )
        snapshot = store.list_dataset_snapshots(cohort_id=training.cohort.cohort_id)[0]

        evaluation = freeze_cohort(
            store=store,
            slice_id="slice.capture",
            name="capture-eval",
            run_id="run_3",
            purpose="evaluation",
        )
        suite = create_eval_suite_from_cohort(
            store=store,
            slice_id="slice.capture",
            suite_kind="offline_test",
            cohort_id=evaluation.cohort.cohort_id,
            name="capture-offline",
            dataset_snapshot_id=snapshot.dataset_snapshot_id,
        )
        scorecard = record_scorecard(
            store=store,
            eval_suite_id=suite.eval_suite_id,
            candidate_model="small-v1",
            baseline_model="large-v1",
            metrics={
                "task_success_rate": 0.98,
                "verifier_pass_rate": 0.95,
                "p95_latency": 410,
            },
            thresholds={
                "task_success_rate": {"op": "gte", "value": 0.95},
                "verifier_pass_rate": {"op": "gte", "value": 0.90},
                "p95_latency": {"op": "lte", "value": 500},
            },
        )
        record_promotion_decision(
            store=store,
            scorecard_id=scorecard.scorecard_id,
            stage="offline",
            coverage_policy_version="coverage.v1",
            summary="dashboard smoke passed",
            rollback_conditions=["verifier_pass_rate_drop"],
        )
        enqueue_feedback(
            store=store,
            slice_id="slice.capture",
            source="shadow_disagreement",
            target_ref="run:run_2",
            reason="unannotated run should be reviewed",
            payload={"session_id": "session_1", "run_id": "run_2"},
        )
        return store

    def _append_run(
        self,
        *,
        store: SQLiteFactStore,
        session_id: str,
        run_id: str,
        prompt: str,
        response_text: str,
        task_instance_key: str,
        template_hash: str,
        with_annotation: bool,
        semantic_kinds: list[str] | None = None,
    ) -> None:
        request_id = f"req_{run_id}"
        request = new_fact_event(
            run_id=run_id,
            session_id=session_id,
            actor="model",
            kind="request_started",
            payload={
                "path": "/v1/chat/completions",
                "json": {"messages": [{"role": "user", "content": prompt}]},
            },
            request_id=request_id,
        )
        facts = [request]
        for semantic_kind in semantic_kinds or []:
            facts.append(
                new_semantic_event_fact(
                    run_id=run_id,
                    session_id=session_id,
                    semantic_kind=semantic_kind,
                    payload={"request_id": request_id},
                    request_id=request_id,
                )
            )
        facts.append(
            new_fact_event(
                run_id=run_id,
                session_id=session_id,
                actor="model",
                kind="response_finished",
                payload={
                    "path": "/v1/chat/completions",
                    "status_code": 200,
                    "json": {
                        "choices": [
                            {"message": {"role": "assistant", "content": response_text}}
                        ]
                    },
                },
                request_id=request_id,
                parent_ref=request.fact_id,
            )
        )
        store.append_facts(facts)

        if not with_annotation:
            return

        store.append_artifact(
            new_artifact_record(
                artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
                target_ref=f"run:{run_id}",
                producer="taxonomy.v1",
                payload={
                    "annotation_kind": E1_ANNOTATION_KIND,
                    "task_family": "captured_agent_task",
                    "task_type": "generic_proxy_capture",
                    "task_template_hash": template_hash,
                    "task_instance_key": task_instance_key,
                    "verifier_name": "judge-v1",
                    "verifier_score": 0.95,
                    "quality_confidence": 0.97,
                    "taxonomy_version": "taxonomy.v1",
                    "annotation_version": "e1.v1",
                    "source_channel": "captured",
                },
                session_id=session_id,
                run_id=run_id,
                confidence=0.97,
            )
        )


if __name__ == "__main__":
    unittest.main()
