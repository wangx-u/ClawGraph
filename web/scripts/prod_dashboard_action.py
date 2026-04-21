#!/usr/bin/env python3
"""Execute dashboard and training mutations against a local ClawGraph store."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from clawgraph.control_plane.actions import (  # noqa: E402
    bootstrap_review_action,
    create_handoff_action,
    evaluate_candidate_action,
    resolve_feedback_action,
    review_override_action,
    sync_feedback_queue_action,
    submit_training_request_action,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-dir")
    subparsers = parser.add_subparsers(dest="action", required=True)

    resolve = subparsers.add_parser("resolve-feedback")
    resolve.add_argument("--store", required=True)
    resolve.add_argument("--feedback-id", required=True)
    resolve.add_argument("--status", default="resolved")
    resolve.add_argument("--note")
    resolve.add_argument("--reviewer")

    override = subparsers.add_parser("review-override")
    override.add_argument("--store", required=True)
    override.add_argument("--session-id", required=True)
    override.add_argument("--run-id", required=True)
    override.add_argument("--feedback-id")
    override.add_argument("--feedback-status", default="resolved")
    override.add_argument("--producer", default="dashboard.human_review")
    override.add_argument("--version", default="dashboard.review.v1")
    override.add_argument("--review-note")
    override.add_argument("--reviewer")
    override.add_argument("--quality-confidence", type=float, default=1.0)
    override.add_argument("--verifier-score", type=float, default=1.0)

    sync_feedback = subparsers.add_parser("sync-feedback")
    sync_feedback.add_argument("--store", required=True)
    sync_feedback.add_argument("--slice-id", required=True)
    sync_feedback.add_argument("--session-id")
    sync_feedback.add_argument("--run-id")
    sync_feedback.add_argument("--task-instance-key")
    sync_feedback.add_argument("--task-template-hash")
    sync_feedback.add_argument("--source", default="dashboard.review_sync")
    sync_feedback.add_argument("--min-quality-confidence", type=float)
    sync_feedback.add_argument("--min-verifier-score", type=float)
    sync_feedback.add_argument("--source-channel")
    sync_feedback.add_argument("--limit", type=int)
    sync_feedback.add_argument("--purpose")

    bootstrap_review = subparsers.add_parser("bootstrap-review")
    bootstrap_review.add_argument("--store", required=True)
    bootstrap_review.add_argument("--session-id", required=True)
    bootstrap_review.add_argument("--run-id", required=True)
    bootstrap_review.add_argument("--slice-id")
    bootstrap_review.add_argument("--slice-owner", default="clawgraph.dashboard")
    bootstrap_review.add_argument("--slice-default-use", default="training_candidate")
    bootstrap_review.add_argument("--slice-risk-level", default="medium")
    bootstrap_review.add_argument("--source", default="dashboard.review_sync")
    bootstrap_review.add_argument("--min-quality-confidence", type=float)
    bootstrap_review.add_argument("--min-verifier-score", type=float)
    bootstrap_review.add_argument("--purpose")

    submit = subparsers.add_parser("submit-training")
    submit.add_argument("--store", required=True)
    submit.add_argument("--request-id")
    submit.add_argument("--manifest-path")
    submit.add_argument("--executor-ref")
    submit.add_argument("--candidate-out")

    evaluate = subparsers.add_parser("evaluate-candidate")
    evaluate.add_argument("--store", required=True)
    evaluate.add_argument("--candidate-id")
    evaluate.add_argument("--manifest-path")
    evaluate.add_argument("--eval-suite-id")
    evaluate.add_argument("--baseline-model")
    evaluate.add_argument("--baseline-model-path")
    evaluate.add_argument("--sample-ref")
    evaluate.add_argument("--grader-name", default="exact-match")
    evaluate.add_argument("--grader-ref")
    evaluate.add_argument("--max-tokens", type=int, default=512)
    evaluate.add_argument("--temperature", type=float, default=0.0)
    evaluate.add_argument("--top-p", type=float, default=1.0)
    evaluate.add_argument("--base-url")
    evaluate.add_argument("--promotion-stage", default="offline")
    evaluate.add_argument("--coverage-policy-version", default="logits.eval.v1")
    evaluate.add_argument("--promotion-summary")
    evaluate.add_argument("--output-path")

    handoff = subparsers.add_parser("create-handoff")
    handoff.add_argument("--store", required=True)
    handoff.add_argument("--candidate-id")
    handoff.add_argument("--manifest-path")
    handoff.add_argument("--promotion-decision-id")
    handoff.add_argument("--output-path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.action == "resolve-feedback":
        payload = resolve_feedback_action(
            store_uri=args.store,
            feedback_id=args.feedback_id,
            status=args.status,
            note=args.note,
            reviewer=args.reviewer or "dashboard.local",
        )
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return 0

    if args.action == "review-override":
        payload = review_override_action(
            store_uri=args.store,
            session_id=args.session_id,
            run_id=args.run_id,
            feedback_id=args.feedback_id,
            feedback_status=args.feedback_status,
            producer=args.producer,
            version=args.version,
            review_note=args.review_note,
            reviewer=args.reviewer or "dashboard.local",
            quality_confidence=args.quality_confidence,
            verifier_score=args.verifier_score,
        )
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return 0

    if args.action == "sync-feedback":
        payload = sync_feedback_queue_action(
            store_uri=args.store,
            slice_id=args.slice_id,
            session_id=args.session_id,
            run_id=args.run_id,
            task_instance_key=args.task_instance_key,
            task_template_hash=args.task_template_hash,
            source=args.source,
            min_quality_confidence=args.min_quality_confidence,
            min_verifier_score=args.min_verifier_score,
            source_channel=args.source_channel,
            limit=args.limit,
            purpose=args.purpose,
        )
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return 0

    if args.action == "bootstrap-review":
        payload = bootstrap_review_action(
            store_uri=args.store,
            session_id=args.session_id,
            run_id=args.run_id,
            slice_id=args.slice_id,
            slice_owner=args.slice_owner,
            slice_default_use=args.slice_default_use,
            slice_risk_level=args.slice_risk_level,
            source=args.source,
            min_quality_confidence=args.min_quality_confidence,
            min_verifier_score=args.min_verifier_score,
            purpose=args.purpose,
        )
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return 0

    if args.action == "submit-training":
        payload = submit_training_request_action(
            store_uri=args.store,
            manifest_dir=args.manifest_dir,
            request_id=args.request_id,
            manifest_path=args.manifest_path,
            executor_ref=args.executor_ref,
            candidate_out=args.candidate_out,
        )
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return 0

    if args.action == "evaluate-candidate":
        payload = evaluate_candidate_action(
            store_uri=args.store,
            manifest_dir=args.manifest_dir,
            candidate_id=args.candidate_id,
            manifest_path=args.manifest_path,
            eval_suite_id=args.eval_suite_id,
            baseline_model=args.baseline_model,
            baseline_model_path=args.baseline_model_path,
            sample_ref=args.sample_ref,
            grader_name=args.grader_name,
            grader_ref=args.grader_ref,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            base_url=args.base_url,
            promotion_stage=args.promotion_stage,
            coverage_policy_version=args.coverage_policy_version,
            promotion_summary=args.promotion_summary,
            output_path=args.output_path,
        )
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return 0

    if args.action == "create-handoff":
        payload = create_handoff_action(
            store_uri=args.store,
            manifest_dir=args.manifest_dir,
            candidate_id=args.candidate_id,
            manifest_path=args.manifest_path,
            promotion_decision_id=args.promotion_decision_id,
            output_path=args.output_path,
        )
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return 0

    raise SystemExit(f"unsupported action: {args.action}")


if __name__ == "__main__":
    raise SystemExit(main())
