#!/usr/bin/env python3
"""Seed one deterministic local store for dashboard e2e coverage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from clawgraph.protocol.factories import (  # noqa: E402
    new_artifact_record,
    new_cohort_member_record,
    new_cohort_record,
    new_dataset_snapshot_record,
    new_eval_suite_record,
    new_fact_event,
    new_feedback_queue_record,
    new_promotion_decision_record,
    new_scorecard_record,
    new_semantic_event_fact,
    new_slice_record,
)
from clawgraph.integrations.logits import save_manifest  # noqa: E402
from clawgraph.integrations.logits.manifests import (  # noqa: E402
    EvalExecutionManifest,
    ModelCandidateManifest,
    RouterHandoffManifest,
    TrainingRequestManifest,
)
from clawgraph.store import SQLiteFactStore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--manifest-dir")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _reset_sqlite_store(args.store)
    store = SQLiteFactStore(args.store)

    slice_record = new_slice_record(
        slice_id="slice.capture.e2e",
        task_family="benchmark_coding_task",
        task_type="swebench_issue_fix",
        taxonomy_version="benchmark.swebench.v1",
        sample_unit="run",
        verifier_contract="benchmark.verifier.v1",
        risk_level="medium",
        default_use="training_candidate",
        owner="benchmark-team",
        description="SWE-bench Lite benchmark issue fixing"
    )
    store.put_slice(slice_record)

    train_request = new_fact_event(
        run_id="run_train_e2e",
        session_id="session_train_e2e",
        actor="model",
        kind="request_started",
        payload={
            "path": "/chat/completions",
            "json": {"messages": [{"role": "user", "content": "Fix sqlfluff issue 1625"}]}
        },
        request_id="req_train_e2e",
    )
    train_response = new_fact_event(
        run_id="run_train_e2e",
        session_id="session_train_e2e",
        actor="model",
        kind="response_finished",
        payload={
            "path": "/chat/completions",
            "status_code": 200,
            "total_latency_ms": 420,
            "json": {"choices": [{"message": {"role": "assistant", "content": "Prepared patch"}}]},
        },
        request_id="req_train_e2e",
        parent_ref=train_request.fact_id,
    )
    train_semantic = new_semantic_event_fact(
        run_id="run_train_e2e",
        session_id="session_train_e2e",
        semantic_kind="task_completed",
        request_id="req_train_e2e",
    )

    eval_request = new_fact_event(
        run_id="run_eval_e2e",
        session_id="session_eval_e2e",
        actor="model",
        kind="request_started",
        payload={
            "path": "/chat/completions",
            "json": {"messages": [{"role": "user", "content": "Fix sqlfluff issue 2419"}]}
        },
        request_id="req_eval_e2e",
    )
    eval_response = new_fact_event(
        run_id="run_eval_e2e",
        session_id="session_eval_e2e",
        actor="model",
        kind="response_finished",
        payload={
            "path": "/chat/completions",
            "status_code": 200,
            "total_latency_ms": 510,
            "json": {"choices": [{"message": {"role": "assistant", "content": "Prepared holdout patch"}}]},
        },
        request_id="req_eval_e2e",
        parent_ref=eval_request.fact_id,
    )
    store.append_facts(
        [
            train_request,
            train_response,
            train_semantic,
            eval_request,
            eval_response,
        ]
    )

    train_annotation = new_artifact_record(
        artifact_type="annotation",
        target_ref="run:run_train_e2e",
        producer="seed.annotation",
        version="seed.v1",
        session_id="session_train_e2e",
        run_id="run_train_e2e",
        confidence=0.96,
        payload={
            "annotation_kind": "e1",
            "task_family": "benchmark_coding_task",
            "task_type": "swebench_issue_fix",
            "task_template_hash": "tmpl_train_e2e",
            "task_instance_key": "sqlfluff__sqlfluff-1625",
            "verifier_name": "benchmark.verifier.v1",
            "verifier_score": 0.94,
            "quality_confidence": 0.96,
            "taxonomy_version": "benchmark.swebench.v1",
            "annotation_version": "benchmark.swebench.e1.v1",
            "source_channel": "benchmark.swebench_lite",
            "review_reasons": [],
        },
    )
    eval_annotation = new_artifact_record(
        artifact_type="annotation",
        target_ref="run:run_eval_e2e",
        producer="seed.annotation",
        version="seed.v1",
        session_id="session_eval_e2e",
        run_id="run_eval_e2e",
        confidence=0.95,
        payload={
            "annotation_kind": "e1",
            "task_family": "benchmark_coding_task",
            "task_type": "swebench_issue_fix",
            "task_template_hash": "tmpl_eval_e2e",
            "task_instance_key": "sqlfluff__sqlfluff-2419",
            "verifier_name": "benchmark.verifier.v1",
            "verifier_score": 0.95,
            "quality_confidence": 0.95,
            "taxonomy_version": "benchmark.swebench.v1",
            "annotation_version": "benchmark.swebench.e1.v1",
            "source_channel": "benchmark.swebench_lite",
            "review_reasons": [],
        },
    )
    eval_score = new_artifact_record(
        artifact_type="score",
        target_ref="run:run_eval_e2e",
        producer="seed.eval",
        version="seed.v1",
        session_id="session_eval_e2e",
        run_id="run_eval_e2e",
        confidence=0.95,
        payload={
            "score": 1.0,
            "label": True,
            "metric_name": "benchmark_pass",
        },
    )
    store.append_artifacts([train_annotation, eval_annotation, eval_score])

    cohort_train = new_cohort_record(
        cohort_id="cohort_train_e2e",
        name="SQLFluff 训练批次",
        slice_ids=[slice_record.slice_id],
        manifest={
            "expected_use": "training",
            "selection_query": {
                "task_family": "benchmark_coding_task",
                "task_type": "swebench_issue_fix",
                "source_channel": "benchmark.swebench_lite",
            },
            "time_range": {
                "start": train_request.timestamp.isoformat(),
                "end": train_response.timestamp.isoformat(),
            },
            "quality": {
                "quality_gate": {
                    "min_quality_confidence": 0.9,
                    "min_verifier_score": 0.9,
                    "version": "seed.curation.v1",
                }
            },
            "split_counts": {"train": 1, "val": 0, "test": 0},
            "review": {"status": "clear", "queue": []},
            "artifact_view": {"strategy": "frozen_artifact_ids"},
        },
        metadata={"created_from": "seed"},
    )
    cohort_train.manifest["cohort_id"] = cohort_train.cohort_id
    cohort_eval = new_cohort_record(
        cohort_id="cohort_eval_e2e",
        name="SQLFluff 验证批次",
        slice_ids=[slice_record.slice_id],
        manifest={
            "expected_use": "evaluation",
            "selection_query": {
                "task_family": "benchmark_coding_task",
                "task_type": "swebench_issue_fix",
                "source_channel": "benchmark.swebench_lite",
            },
            "time_range": {
                "start": eval_request.timestamp.isoformat(),
                "end": eval_response.timestamp.isoformat(),
            },
            "quality": {
                "quality_gate": {
                    "min_quality_confidence": 0.9,
                    "min_verifier_score": 0.9,
                    "version": "seed.curation.v1",
                }
            },
            "split_counts": {"train": 0, "val": 1, "test": 0},
            "review": {"status": "clear", "queue": []},
            "artifact_view": {"strategy": "frozen_artifact_ids"},
        },
        metadata={"created_from": "seed"},
    )
    cohort_eval.manifest["cohort_id"] = cohort_eval.cohort_id
    store.append_cohort(
        cohort_train,
        members=[
            new_cohort_member_record(
                cohort_id=cohort_train.cohort_id,
                slice_id=slice_record.slice_id,
                session_id="session_train_e2e",
                run_id="run_train_e2e",
                annotation_artifact_id=train_annotation.artifact_id,
                task_instance_key="sqlfluff__sqlfluff-1625",
                task_template_hash="tmpl_train_e2e",
                quality_confidence=0.96,
                verifier_score=0.94,
                source_channel="benchmark.swebench_lite",
            )
        ],
    )
    store.append_cohort(
        cohort_eval,
        members=[
            new_cohort_member_record(
                cohort_id=cohort_eval.cohort_id,
                slice_id=slice_record.slice_id,
                session_id="session_eval_e2e",
                run_id="run_eval_e2e",
                annotation_artifact_id=eval_annotation.artifact_id,
                task_instance_key="sqlfluff__sqlfluff-2419",
                task_template_hash="tmpl_eval_e2e",
                quality_confidence=0.95,
                verifier_score=0.95,
                source_channel="benchmark.swebench_lite",
            )
        ],
    )

    snapshot = new_dataset_snapshot_record(
        dataset_snapshot_id="ds_e2e_sft",
        dataset_recipe_id="recipe_e2e_sft",
        builder="sft",
        sample_unit="run",
        cohort_id=cohort_train.cohort_id,
        output_path="/tmp/clawgraph-e2e/sft.jsonl",
        record_count=1,
        manifest={
            "dataset_snapshot_id": "ds_e2e_sft",
            "builder": "sft",
            "sample_unit": "run",
            "time_range": {
                "start": train_request.timestamp.isoformat(),
                "end": train_response.timestamp.isoformat(),
            },
            "taxonomy_versions": ["benchmark.swebench.v1"],
            "split": {
                "strategy": "seed_guard",
                "counts": {"train": 1, "val": 0, "test": 0},
            },
            "cohort_contract": {
                "expected_use": "training",
                "quality_gate": {
                    "min_quality_confidence": 0.9,
                    "min_verifier_score": 0.9,
                },
            },
        },
        metadata={"session_id": "session_train_e2e", "run_id": "run_train_e2e"},
    )
    store.append_dataset_snapshot(snapshot)

    suite = new_eval_suite_record(
        eval_suite_id="eval_e2e_offline",
        slice_id=slice_record.slice_id,
        suite_kind="offline_test",
        name="SQLFluff 离线验证",
        cohort_id=cohort_eval.cohort_id,
        dataset_snapshot_id=snapshot.dataset_snapshot_id,
        manifest={
            "slice_id": slice_record.slice_id,
            "cohort_id": cohort_eval.cohort_id,
            "dataset_snapshot_id": snapshot.dataset_snapshot_id,
            "task_instance_count": 1,
            "run_count": 1,
            "expected_use": "evaluation",
            "time_range": {
                "start": eval_request.timestamp.isoformat(),
                "end": eval_response.timestamp.isoformat(),
            },
        },
        metadata={"source": "seed"},
    )
    store.append_eval_suite(suite)

    scorecard = new_scorecard_record(
        scorecard_id="score_e2e_offline",
        eval_suite_id=suite.eval_suite_id,
        slice_id=slice_record.slice_id,
        candidate_model="mini-e2e",
        baseline_model="teacher-e2e",
        verdict="pass",
        metrics={
            "task_success_rate": 1.0,
            "verifier_pass_rate": 1.0,
            "p95_latency": 510,
            "fallback_rate": 0.0,
        },
        thresholds={
            "task_success_rate": {"op": "gte", "value": 0.8},
            "verifier_pass_rate": {"op": "gte", "value": 0.8},
            "p95_latency": {"op": "lte", "value": 5000},
        },
        metadata={"summary": "seeded benchmark pass"},
    )
    store.append_scorecard(scorecard)
    promotion = new_promotion_decision_record(
        promotion_decision_id="decision_e2e_canary",
        slice_id=slice_record.slice_id,
        scorecard_id=scorecard.scorecard_id,
        stage="canary",
        decision="promote",
        coverage_policy_version="coverage.seed.v1",
        summary="seeded benchmark promotion decision",
        rollback_conditions=["verifier_pass_rate_drop > 0.03", "fallback_rate > 0.10"],
        metadata={"seed": True},
    )
    store.append_promotion_decision(promotion)

    feedback = new_feedback_queue_record(
        feedback_id="fb_e2e_review",
        slice_id=slice_record.slice_id,
        source="seed.review",
        target_ref="run:run_train_e2e",
        reason="需要人工确认该轨迹是否可进入训练集",
        payload={
            "session_id": "session_train_e2e",
            "run_id": "run_train_e2e",
        },
    )
    store.append_feedback_queue_item(feedback)
    if args.manifest_dir:
        _seed_training_manifests(
            manifest_dir=Path(args.manifest_dir),
            dataset_snapshot_id=snapshot.dataset_snapshot_id,
            eval_suite_id=suite.eval_suite_id,
            slice_id=slice_record.slice_id,
        )
    return 0


def _reset_sqlite_store(store_uri: str) -> None:
    if not store_uri.startswith("sqlite:///"):
        return
    parsed = urlparse(store_uri)
    db_path = Path(unquote(parsed.path))
    if db_path.exists():
        db_path.unlink()


def _seed_training_manifests(
    *,
    manifest_dir: Path,
    dataset_snapshot_id: str,
    eval_suite_id: str,
    slice_id: str,
) -> None:
    manifest_dir.mkdir(parents=True, exist_ok=True)

    training_request = TrainingRequestManifest(
        training_request_id="train_e2e_sft",
        created_at="2026-04-16T09:30:00+00:00",
        recipe_family="sft",
        recipe_name="supervised.chat_sl",
        base_model="mini-e2e-base",
        dataset_snapshot_id=dataset_snapshot_id,
        dataset_builder="sft",
        input_path="/tmp/clawgraph-e2e/sft.jsonl",
        eval_suite_id=eval_suite_id,
        log_path="/tmp/clawgraph-e2e/logits/train_e2e_sft",
        runtime_config={"executor_ref": "seed.executor"},
        metadata={"seed": True},
    )
    candidate = ModelCandidateManifest(
        candidate_model_id="cand_e2e_sft",
        created_at="2026-04-16T10:10:00+00:00",
        training_request_id=training_request.training_request_id,
        recipe_family="sft",
        training_recipe="supervised.chat_sl",
        base_model=training_request.base_model,
        dataset_snapshot_id=dataset_snapshot_id,
        dataset_builder="sft",
        candidate_model="mini-e2e",
        checkpoint_path="/tmp/clawgraph-e2e/logits/checkpoints/mini-e2e",
        sampler_path="/tmp/clawgraph-e2e/logits/samplers/mini-e2e",
        published_model_path="logits://mini-e2e",
        log_path=training_request.log_path,
        metadata={"seed": True},
    )
    execution = EvalExecutionManifest(
        eval_execution_id="evalexec_e2e_sft",
        created_at="2026-04-16T10:40:00+00:00",
        eval_suite_id=eval_suite_id,
        candidate_model_id=candidate.candidate_model_id,
        candidate_model=candidate.candidate_model or "mini-e2e",
        candidate_model_path=candidate.published_model_path,
        baseline_model="teacher-e2e",
        baseline_model_path="logits://teacher-e2e",
        grader_name="benchmark-grader",
        case_count=1,
        scorecard_id="score_e2e_offline",
        promotion_decision_id="decision_e2e_canary",
        metrics={"task_success_rate": 1.0, "verifier_pass_rate": 1.0},
        thresholds={"task_success_rate": {"op": "gte", "value": 0.8}},
        metadata={"seed": True},
    )
    handoff = RouterHandoffManifest(
        handoff_id="handoff_e2e_sft",
        created_at="2026-04-16T10:55:00+00:00",
        promotion_decision_id="decision_e2e_canary",
        scorecard_id="score_e2e_offline",
        candidate_model_id=candidate.candidate_model_id,
        candidate_model=candidate.candidate_model or "mini-e2e",
        candidate_model_path=candidate.published_model_path,
        slice_id=slice_id,
        stage="canary",
        decision="promote",
        coverage_policy_version="coverage.seed.v1",
        route_config={
            "slice_id": slice_id,
            "route_mode": "canary",
            "candidate_model": candidate.candidate_model or "mini-e2e",
            "candidate_model_path": candidate.published_model_path,
            "baseline_model": "teacher-e2e",
            "fallback": {
                "target_model": "teacher-e2e",
                "conditions": ["verifier_pass_rate_drop > 0.03", "fallback_rate > 0.10"],
            },
        },
        rollback_conditions=["verifier_pass_rate_drop > 0.03", "fallback_rate > 0.10"],
        metadata={"seed": True},
    )

    save_manifest(training_request, manifest_dir / "training_request.e2e.json")
    save_manifest(candidate, manifest_dir / "candidate.e2e.json")
    save_manifest(execution, manifest_dir / "eval_execution.e2e.json")
    save_manifest(handoff, manifest_dir / "router_handoff.e2e.json")


if __name__ == "__main__":
    raise SystemExit(main())
