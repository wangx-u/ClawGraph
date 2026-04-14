#!/usr/bin/env python3
"""Execute dashboard mutations against a local ClawGraph store."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from clawgraph.evaluation import update_feedback_queue_status  # noqa: E402
from clawgraph.judge import plan_review_override  # noqa: E402
from clawgraph.protocol.models import ArtifactRecord  # noqa: E402
from clawgraph.store import SQLiteFactStore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.action == "resolve-feedback":
        payload = {
            "action": args.action,
            "items": [
                item.to_dict()
                for item in update_feedback_queue_status(
                    store_uri=args.store,
                    feedback_id=args.feedback_id,
                    status=args.status,
                    note=args.note,
                    reviewer=args.reviewer,
                )
            ],
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return 0

    if args.action == "review-override":
        store = SQLiteFactStore(args.store)
        facts = store.list_facts(session_id=args.session_id, run_id=args.run_id)
        if not facts:
            raise SystemExit(f"no facts found for {args.session_id}/{args.run_id}")
        artifacts = store.list_artifacts(
            session_id=args.session_id,
            run_id=args.run_id,
            latest_only=True,
        )
        plan = plan_review_override(
            facts=facts,
            artifacts=artifacts,
            producer=args.producer,
            version=args.version,
            review_note=args.review_note,
            payload_patch={
                "quality_confidence": args.quality_confidence,
                "verifier_score": args.verifier_score,
            },
        )
        persisted, skipped = _persist_unique_artifacts(
            store=store,
            session_id=args.session_id,
            run_id=args.run_id,
            artifacts=[plan.artifact],
        )
        feedback_items = []
        if args.feedback_id:
            feedback_items = [
                item.to_dict()
                for item in update_feedback_queue_status(
                    store=store,
                    feedback_id=args.feedback_id,
                    status=args.feedback_status,
                    note=args.review_note,
                    reviewer=args.reviewer,
                )
            ]
        payload = {
            "action": args.action,
            "persisted_count": len(persisted),
            "skipped_duplicates": skipped,
            "artifact_id": persisted[0].artifact_id if persisted else None,
            "run_id": args.run_id,
            "session_id": args.session_id,
            "feedback_items": feedback_items,
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return 0

    raise SystemExit(f"unsupported action: {args.action}")


def _persist_unique_artifacts(
    *,
    store: SQLiteFactStore,
    session_id: str,
    run_id: str,
    artifacts: list[ArtifactRecord],
) -> tuple[list[ArtifactRecord], int]:
    existing = store.list_artifacts(session_id=session_id, run_id=run_id, latest_only=True)
    seen = {_artifact_signature(artifact) for artifact in existing}
    persisted: list[ArtifactRecord] = []
    skipped = 0
    for artifact in artifacts:
        signature = _artifact_signature(artifact)
        if signature in seen:
            skipped += 1
            continue
        persisted.append(artifact)
        seen.add(signature)
    if persisted:
        store.append_artifacts(persisted)
    return persisted, skipped


def _artifact_signature(artifact: ArtifactRecord) -> str:
    return json.dumps(
        {
            "artifact_type": artifact.artifact_type,
            "target_ref": artifact.target_ref,
            "producer": artifact.producer,
            "version": artifact.version,
            "session_id": artifact.session_id,
            "run_id": artifact.run_id,
            "status": artifact.status,
            "payload": artifact.payload,
            "metadata": artifact.metadata,
            "supersedes_artifact_id": artifact.supersedes_artifact_id,
        },
        ensure_ascii=True,
        sort_keys=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
