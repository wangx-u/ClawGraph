"""Web-dashboard bundle builders backed by shared ClawGraph read models."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
from typing import Any

from clawgraph.curation import list_slice_candidates
from clawgraph.dashboard import DashboardRunRow, build_dashboard_snapshot
from clawgraph.export import build_dataset_readiness_summary
from clawgraph.graph import (
    build_branch_inspect_summaries,
    build_request_span_summaries,
    build_session_inspect_summary,
)
from clawgraph.integrations.logits.manifests import (
    EvalExecutionManifest,
    ModelCandidateManifest,
    RouterHandoffManifest,
    TrainingRequestManifest,
    load_manifest as load_logits_manifest,
)
from clawgraph.integrations.logits.registry import build_training_registry
from clawgraph.query import ClawGraphQueryService
from clawgraph.store import SQLiteFactStore


def normalize_store_uri(store_uri: str) -> str:
    """Normalize relative sqlite paths for web bridge entrypoints."""

    if store_uri.startswith("sqlite:///"):
        raw_path = store_uri.removeprefix("sqlite:///")
        if raw_path and not raw_path.startswith("/"):
            return f"sqlite://{(Path.cwd() / raw_path).resolve()}"
        return store_uri

    if store_uri.startswith("sqlite://"):
        raw_path = store_uri.removeprefix("sqlite://")
        if raw_path and not raw_path.startswith("/"):
            return f"sqlite://{(Path.cwd() / raw_path).resolve()}"
        return store_uri

    resolved = Path(store_uri).expanduser()
    if not resolved.is_absolute():
        resolved = (Path.cwd() / resolved).resolve()
    return f"sqlite://{resolved}"


def build_web_dashboard_bundle(
    *,
    store_uri: str | None = None,
    store: SQLiteFactStore | None = None,
    manifest_dir: str | None = None,
    session_limit: int = 12,
    run_limit: int = 24,
    artifact_limit: int = 40,
) -> dict[str, Any]:
    """Build the web dashboard bundle from the shared snapshot plus live store details."""

    if store is None and store_uri is None:
        raise ValueError("store or store_uri is required")

    resolved_store = store or SQLiteFactStore(str(store_uri))
    service = ClawGraphQueryService(store=resolved_store)
    all_run_ids = list(resolved_store.iter_runs())
    snapshot = build_dashboard_snapshot(
        store=resolved_store,
        session_limit=session_limit,
        run_limit=max(run_limit, len(all_run_ids)),
    )
    run_rows_by_id = {row.run_id: row for row in snapshot.recent_runs}
    workflow_rows_by_id = {row.run_id: row for row in snapshot.workflow_runs}
    session_rows_by_id = {row.session_id: row for row in snapshot.recent_sessions}

    session_ids = list(resolved_store.iter_sessions())[:session_limit]
    sessions_payload: list[dict[str, Any]] = []
    replay_payload: list[dict[str, Any]] = []
    recent_artifact_map: dict[str, dict[str, Any]] = {}
    run_display_map: dict[str, dict[str, Any]] = {}
    session_display_map: dict[str, dict[str, Any]] = {}
    readiness_accumulator: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"ready_runs": 0, "predicted_records": 0, "blockers": set()}
    )
    all_runs: list[dict[str, Any]] = []
    training_registry = build_training_registry(
        manifest_dir=manifest_dir,
        store=resolved_store,
    )

    for session_id in session_ids:
        facts = resolved_store.list_facts(session_id=session_id)
        if not facts:
            continue
        artifacts = resolved_store.list_artifacts(session_id=session_id, latest_only=True)
        session_inspect = build_session_inspect_summary(facts, artifacts)
        run_ids = list(resolved_store.iter_runs(session_id=session_id))
        run_payloads: list[dict[str, Any]] = []
        session_anomalies: list[str] = []

        for artifact in artifacts:
            recent_artifact_map[artifact.artifact_id] = {
                "id": artifact.artifact_id,
                "type": artifact.artifact_type,
                "targetRef": artifact.target_ref,
                "producer": artifact.producer,
                "status": artifact.status,
                "confidence": "-" if artifact.confidence is None else f"{artifact.confidence:.2f}",
                "version": artifact.version or "-",
            }

        for run_id in run_ids:
            run_facts = resolved_store.list_facts(run_id=run_id)
            run_artifacts = resolved_store.list_artifacts(
                session_id=session_id,
                run_id=run_id,
                latest_only=True,
            )
            annotation_payload = active_run_annotation_payload(run_artifacts)
            request_summaries = build_request_span_summaries(run_facts, run_artifacts)
            branch_summaries = build_branch_inspect_summaries(run_facts, run_artifacts)
            readiness_summary = build_dataset_readiness_summary(run_facts, run_artifacts)
            request_fact_map = {
                fact.request_id: fact
                for fact in run_facts
                if fact.kind == "request_started" and isinstance(fact.request_id, str)
            }
            declared_count = sum(1 for branch in branch_summaries if branch.source == "declared")
            declared_ratio = declared_count / len(branch_summaries) if branch_summaries else 1.0
            run_row = run_rows_by_id.get(run_id)
            if run_row is None:
                raise ValueError(f"dashboard snapshot missing run row: {run_id}")
            workflow_row = workflow_rows_by_id.get(run_id)
            if workflow_row is None:
                raise ValueError(f"dashboard snapshot missing workflow row: {run_id}")

            run_title = describe_run_title(
                task_family=run_row.task_family,
                task_type=run_row.task_type,
                task_instance_key=run_row.task_instance_key,
                annotation_payload=annotation_payload,
            )
            run_summary = describe_run_summary(
                task_family=run_row.task_family,
                task_type=run_row.task_type,
                task_instance_key=run_row.task_instance_key,
                annotation_payload=annotation_payload,
            )
            task_instance_key = (
                run_row.task_instance_key
                if isinstance(run_row.task_instance_key, str)
                else annotation_payload.get("task_instance_key")
                if isinstance(annotation_payload.get("task_instance_key"), str)
                else None
            )
            task_instance_name = describe_task_instance(
                task_instance_key=task_instance_key,
                annotation_payload=annotation_payload,
            )

            run_payload = {
                "id": run_id,
                "title": run_title,
                "summary": run_summary,
                "taskLabel": task_label(run_row.task_family, run_row.task_type),
                "taskInstanceKey": task_instance_key,
                "taskInstanceLabel": task_instance_name,
                "repo": annotation_payload.get("repo") if isinstance(annotation_payload.get("repo"), str) else None,
                "requestCount": run_row.request_count,
                "successCount": run_row.success_count,
                "failureCount": run_row.failure_count,
                "openCount": run_row.open_count,
                "branchCount": run_row.branch_count,
                "declaredRatio": round(declared_ratio, 3),
                "artifactCount": run_row.artifact_count,
                "evidenceLevel": run_row.evidence_level,
                "readyBuilders": list(run_row.ready_builders),
                "readinessBlockers": sorted(
                    {
                        blocker
                        for blockers in run_row.readiness_blockers.values()
                        for blocker in blockers
                    }
                )[:3],
                "avgLatency": format_latency(_avg_latency_ms(request_summaries)),
                "outcome": _run_outcome(request_summaries),
                "stage": workflow_row.stage,
                "stageLabel": workflow_row.stage_label,
                "stageDetail": workflow_row.stage_detail,
                "nextAction": workflow_row.next_action,
                "blockers": list(workflow_row.blockers[:3]),
                "reviewStatus": workflow_row.review_status,
                "reviewReasons": list(workflow_row.review_reasons[:3]),
            }
            run_display_map[run_id] = {
                "title": run_title,
                "summary": run_summary,
                "taskInstanceLabel": task_instance_name,
                "taskLabel": task_label(run_row.task_family, run_row.task_type),
            }
            run_payloads.append(run_payload)
            all_runs.append(run_payload)
            session_anomalies.extend(
                run_anomalies(
                    run_title=run_title,
                    run_row=run_row,
                    declared_ratio=declared_ratio,
                    request_summaries=request_summaries,
                )
            )
            readiness_items = {
                item.builder: item
                for item in readiness_summary.builders
                if item.builder in run_row.builder_readiness
            }
            for builder_name, ready in run_row.builder_readiness.items():
                readiness_accumulator[builder_name]["ready_runs"] += 1 if ready else 0
                readiness_accumulator[builder_name]["predicted_records"] += readiness_items[
                    builder_name
                ].predicted_records
                for blocker in run_row.readiness_blockers.get(builder_name, []):
                    readiness_accumulator[builder_name]["blockers"].add(blocker)

            timeline_steps = [fact_timeline_step(fact) for fact in run_facts[:18]]
            replay_payload.append(
                {
                    "sessionId": session_id,
                    "runId": run_id,
                    "title": run_title,
                    "summary": run_summary,
                    "outcome": run_payload["outcome"],
                    "timeline": [step["label"] for step in timeline_steps],
                    "timelineSteps": timeline_steps,
                    "branches": [
                        {
                            "id": branch.branch_id,
                            "title": describe_branch_title(branch.branch_type, branch.source),
                            "summary": describe_branch_summary(
                                branch_type=branch.branch_type,
                                source=branch.source,
                                request_ids=branch.request_ids,
                                parent_id=branch.parent_branch_id,
                            ),
                            "type": branch.branch_type,
                            "status": branch.status,
                            "source": branch.source,
                            "parentId": branch.parent_branch_id,
                            "requestCount": len(branch.request_ids),
                            "requestIds": branch.request_ids,
                        }
                        for branch in branch_summaries
                    ],
                    "requests": [
                        {
                            "id": summary.request_id,
                            "actor": safe_actor(summary.actor),
                            "path": summary.path,
                            "pathLabel": endpoint_label(summary.path, safe_actor(summary.actor)),
                            "stepType": endpoint_step_type(summary.path, safe_actor(summary.actor)),
                            "summary": describe_request_summary(
                                request_summary=summary,
                                request_fact=request_fact_map.get(summary.request_id),
                            ),
                            "outcome": summary.outcome,
                            "status": summary.status_code or (102 if summary.outcome == "open" else 0),
                            "latency": format_latency(summary.total_latency_ms),
                            "artifactCount": summary.artifact_count,
                        }
                        for summary in request_summaries
                    ],
                }
            )

        session_row = session_rows_by_id.get(session_id)
        session_title = describe_session_title(session_id=session_id, run_payloads=run_payloads)
        session_summary = describe_session_summary(
            run_count=len(run_payloads),
            request_count=session_inspect.request_count,
            branch_count=session_inspect.branch_count,
        )
        session_display_map[session_id] = {
            "title": session_title,
            "summary": session_summary,
        }
        sessions_payload.append(
            {
                "id": session_id,
                "title": session_title,
                "summary": session_summary,
                "userIds": session_inspect.user_ids,
                "runs": run_payloads,
                "requests": session_inspect.request_count,
                "branches": session_inspect.branch_count,
                "evidenceLevel": session_row.evidence_level if session_row is not None else "E0",
                "anomalies": list(dict.fromkeys(session_anomalies))[:4],
                "nextAction": run_payloads[0]["nextAction"] if run_payloads else "等待第一条运行进入系统",
            }
        )

    slices = service.list_slices()
    cohorts = service.list_cohorts()
    snapshots = service.list_dataset_snapshots()
    eval_suites = service.list_eval_suites()
    scorecards = service.list_scorecards()
    decisions = service.list_promotion_decisions()
    feedback_items = service.list_feedback_queue()
    slice_lookup = {slice_record.slice_id: slice_record for slice_record in slices}
    slice_label_map = {
        slice_record.slice_id: task_label(slice_record.task_family, slice_record.task_type)
        for slice_record in slices
    }

    holdout_run_ids: set[str] = set()
    cohort_payloads: list[dict[str, Any]] = []
    for cohort in cohorts:
        members = service.list_cohort_members(cohort.cohort_id)
        expected_use = str(cohort.manifest.get("expected_use") or "")
        purpose = "评测" if expected_use == "evaluation" else "训练"
        split_counts = cohort.manifest.get("split_counts")
        holdout_count = 0
        if isinstance(split_counts, dict):
            holdout_count = int(split_counts.get("val", 0)) + int(split_counts.get("test", 0))
        review_payload = cohort.manifest.get("review")
        review_queue = review_payload.get("queue") if isinstance(review_payload, dict) else review_payload
        review_count = len(review_queue) if isinstance(review_queue, list) else 0
        quality_gate = None
        if isinstance(cohort.manifest.get("quality"), dict):
            quality_gate = cohort.manifest["quality"].get("quality_gate")
        if purpose == "评测":
            holdout_run_ids.update(member.run_id for member in members)
        cohort_payloads.append(
            {
                "id": cohort.cohort_id,
                "name": cohort.name,
                "title": cohort.name or cohort.cohort_id,
                "purpose": purpose,
                "expectedUse": expected_use or ("evaluation" if purpose == "评测" else "training"),
                "sliceIds": cohort.slice_ids,
                "sliceLabels": [
                    slice_label_map.get(slice_id, humanize_identifier(slice_id))
                    for slice_id in cohort.slice_ids
                ],
                "selectedCount": len(members),
                "holdoutCount": holdout_count,
                "reviewCount": review_count,
                "timeRange": cohort.manifest.get("time_range")
                if isinstance(cohort.manifest.get("time_range"), dict)
                else None,
                "timeRangeLabel": describe_time_range(cohort.manifest.get("time_range")),
                "selectionSummary": describe_selection_query(cohort.manifest),
                "qualityGate": quality_gate,
                "qualityGateLabel": describe_quality_gate(quality_gate),
                "manifest": cohort.manifest,
            }
        )
    cohort_lookup = {item["id"]: item for item in cohort_payloads}

    candidate_payloads: list[dict[str, Any]] = []
    for slice_record in slices:
        try:
            _, candidates = list_slice_candidates(store=resolved_store, slice_id=slice_record.slice_id, limit=24)
        except ValueError:
            continue
        for candidate in candidates:
            status = "eligible"
            if candidate.run_id in holdout_run_ids:
                status = "holdout"
            elif workflow_rows_by_id.get(candidate.run_id) is not None and workflow_rows_by_id[
                candidate.run_id
            ].review_status in {"feedback", "review"}:
                status = "review"
            candidate_payloads.append(
                {
                    "runId": candidate.run_id,
                    "runTitle": run_display_map.get(candidate.run_id, {}).get("title"),
                    "taskInstanceKey": candidate.task_instance_key,
                    "templateHash": candidate.task_template_hash,
                    "quality": round(candidate.quality_confidence, 4),
                    "verifier": round(candidate.verifier_score, 4),
                    "source": candidate.source_channel,
                    "clusterId": candidate.metadata.get("cluster_keys", {}).get(
                        "task_template",
                        candidate.task_template_hash,
                    ),
                    "status": status,
                    "taskLabel": task_label(candidate.task_family, candidate.task_type),
                }
            )

    slices_payload = [
        {
            "id": slice_record.slice_id,
            "label": slice_label_map.get(slice_record.slice_id, humanize_identifier(slice_record.slice_id)),
            "taskFamily": slice_record.task_family,
            "taskType": slice_record.task_type,
            "taxonomyVersion": slice_record.taxonomy_version,
            "sampleUnit": slice_record.sample_unit,
            "verifierContract": slice_record.verifier_contract,
            "risk": slice_record.risk_level,
            "defaultUse": slice_record.default_use,
            "owner": slice_record.owner,
            "description": slice_record.description,
        }
        for slice_record in slices
    ]
    snapshot_payloads = []
    for snapshot_record in snapshots:
        cohort_payload = (
            cohort_lookup.get(snapshot_record.cohort_id)
            if isinstance(snapshot_record.cohort_id, str)
            else None
        )
        manifest = snapshot_record.manifest if isinstance(snapshot_record.manifest, dict) else {}
        snapshot_payloads.append(
            {
                "id": snapshot_record.dataset_snapshot_id,
                "title": build_snapshot_title(
                    builder=snapshot_record.builder,
                    cohort_name=None if cohort_payload is None else cohort_payload["title"],
                ),
                "builder": snapshot_record.builder,
                "sampleUnit": snapshot_record.sample_unit,
                "cohortId": snapshot_record.cohort_id or "-",
                "cohortName": "-" if cohort_payload is None else cohort_payload["title"],
                "recordCount": snapshot_record.record_count,
                "outputPath": snapshot_record.output_path or "-",
                "createdAt": format_datetime(snapshot_record.created_at),
                "taxonomyVersions": string_list(manifest.get("taxonomy_versions")),
                "timeRange": manifest.get("time_range") if isinstance(manifest.get("time_range"), dict) else None,
                "timeRangeLabel": describe_time_range(manifest.get("time_range")),
                "splitSummary": describe_snapshot_split(manifest),
                "selectionSummary": describe_cohort_contract(manifest.get("cohort_contract")),
                "manifest": manifest,
            }
        )
    snapshot_lookup = {item["id"]: item for item in snapshot_payloads}
    training_registry_summary = training_registry["summary"]
    training_request_payloads = training_registry["training_requests"]
    model_candidate_payloads = training_registry["model_candidates"]
    scorecard_payloads = [
        {
            "id": scorecard.scorecard_id,
            "evalSuiteId": scorecard.eval_suite_id,
            "sliceId": scorecard.slice_id,
            "sliceLabel": slice_label_map.get(scorecard.slice_id, humanize_identifier(scorecard.slice_id)),
            "candidateModel": scorecard.candidate_model,
            "baselineModel": scorecard.baseline_model,
            "verdict": scorecard.verdict,
            "successRate": format_metric(scorecard.metrics, "task_success_rate", "success_rate"),
            "verifierRate": format_metric(scorecard.metrics, "verifier_pass_rate", "verifier_rate"),
            "p95Latency": format_metric(scorecard.metrics, "p95_latency", "p95_latency_ms"),
            "cost": format_metric(scorecard.metrics, "cost_ratio", "unit_cost"),
            "fallbackRate": format_metric(scorecard.metrics, "fallback_rate"),
            "summary": scorecard.metadata.get("summary") if isinstance(scorecard.metadata, dict) else None,
        }
        for scorecard in scorecards
    ]
    eval_suite_payloads = [
        {
            "id": suite.eval_suite_id,
            "name": suite.name,
            "title": suite.name or suite.eval_suite_id,
            "sliceId": suite.slice_id,
            "sliceLabel": slice_label_map.get(suite.slice_id, humanize_identifier(suite.slice_id)),
            "kind": suite.suite_kind,
            "cohortId": suite.cohort_id or "-",
            "cohortName": (
                cohort_lookup[suite.cohort_id]["title"]
                if isinstance(suite.cohort_id, str) and suite.cohort_id in cohort_lookup
                else "-"
            ),
            "datasetSnapshotId": suite.dataset_snapshot_id or "-",
            "datasetSnapshotTitle": (
                snapshot_lookup[suite.dataset_snapshot_id]["title"]
                if isinstance(suite.dataset_snapshot_id, str) and suite.dataset_snapshot_id in snapshot_lookup
                else "-"
            ),
            "status": suite.status,
            "items": int(
                suite.manifest.get("task_instance_count")
                or suite.manifest.get("run_count")
                or suite.manifest.get("session_count")
                or 0
            ),
            "timeRange": suite.manifest.get("time_range")
            if isinstance(suite.manifest.get("time_range"), dict)
            else None,
            "timeRangeLabel": describe_time_range(suite.manifest.get("time_range")),
            "scorecardCount": sum(
                1 for scorecard in scorecards if scorecard.eval_suite_id == suite.eval_suite_id
            ),
            "latestVerdict": next(
                (
                    scorecard.verdict
                    for scorecard in scorecards
                    if scorecard.eval_suite_id == suite.eval_suite_id
                ),
                None,
            ),
            "manifest": suite.manifest,
        }
        for suite in eval_suites
    ]
    eval_execution_payloads = training_registry["eval_executions"]
    router_handoff_payloads = training_registry["router_handoffs"]

    coverage_rows: list[dict[str, Any]] = []
    opportunity_items: list[dict[str, Any]] = []
    coverage_guardrails: set[str] = set()
    for slice_record in slices:
        slice_scorecard = next(
            (scorecard for scorecard in scorecards if scorecard.slice_id == slice_record.slice_id),
            None,
        )
        slice_decision = next(
            (decision for decision in decisions if decision.slice_id == slice_record.slice_id),
            None,
        )
        verdict = verdict_for_records(slice_scorecard, slice_decision)
        recommended_stage = rollout_for_decision(slice_decision)
        recipe_builders = sorted(
            {
                snapshot_record.builder
                for snapshot_record in snapshots
                if snapshot_record.cohort_id is not None
                and any(
                    cohort.cohort_id == snapshot_record.cohort_id
                    and slice_record.slice_id in cohort.slice_ids
                    for cohort in cohorts
                )
            }
        )
        recipe = " + ".join(recipe_builders[:2]) if recipe_builders else "sft"
        opportunity = "阻塞"
        if verdict == "pass" and slice_record.risk_level != "high":
            opportunity = "高"
        elif verdict in {"pass", "hold"}:
            opportunity = "中"
        coverage_rows.append(
            {
                "sliceId": slice_record.slice_id,
                "sliceLabel": slice_label_map.get(slice_record.slice_id, humanize_identifier(slice_record.slice_id)),
                "verifier": strength_for_slice(
                    slice_record,
                    None if slice_scorecard is None else slice_scorecard.metrics,
                ),
                "risk": slice_record.risk_level,
                "complexity": complexity_for_sample_unit(slice_record.sample_unit),
                "recipe": recipe,
                "candidateModel": slice_scorecard.candidate_model if slice_scorecard is not None else "待配置",
                "verdict": verdict,
                "decision": None if slice_decision is None else slice_decision.decision,
                "promotionStage": None if slice_decision is None else slice_decision.stage,
                "recommendedStage": recommended_stage,
                "coveragePolicyVersion": (
                    None if slice_decision is None else slice_decision.coverage_policy_version
                ),
                "rollbackConditions": (
                    [] if slice_decision is None else list(slice_decision.rollback_conditions)
                ),
            }
        )
        if slice_decision is not None:
            coverage_guardrails.update(str(item) for item in slice_decision.rollback_conditions if str(item))
        opportunity_items.append(
            {
                "sliceId": slice_record.slice_id,
                "sliceLabel": slice_label_map.get(slice_record.slice_id, humanize_identifier(slice_record.slice_id)),
                "opportunity": opportunity,
                "reason": f"scorecard={verdict}，risk={slice_record.risk_level}，候选池可见",
                "href": "/coverage",
                "tone": "success" if opportunity == "高" else "warning" if opportunity == "中" else "danger",
            }
        )

    feedback_payloads = []
    for item in feedback_items:
        run_id = None
        if isinstance(item.payload, dict):
            payload_run_id = item.payload.get("run_id")
            if isinstance(payload_run_id, str) and payload_run_id:
                run_id = payload_run_id
        if run_id is None and item.target_ref.startswith("run:"):
            run_id = item.target_ref.split(":", 1)[1]
        run_row = run_rows_by_id.get(run_id) if run_id is not None else None
        workflow_row = workflow_rows_by_id.get(run_id) if run_id is not None else None
        feedback_payloads.append(
            {
                "id": item.feedback_id,
                "source": item.source,
                "targetRef": item.target_ref,
                "targetLabel": (
                    run_display_map.get(run_id, {}).get("title")
                    or run_label(run_row.task_family, run_row.task_type, run_id)
                    if run_row is not None
                    else item.target_ref
                ),
                "runId": run_id,
                "sessionId": (
                    item.payload.get("session_id")
                    if isinstance(item.payload, dict) and isinstance(item.payload.get("session_id"), str)
                    else (None if run_row is None else run_row.session_id)
                ),
                "reason": item.reason,
                "sliceId": item.slice_id,
                "sliceLabel": slice_label_map.get(item.slice_id, humanize_identifier(item.slice_id)),
                "taskLabel": (
                    task_label(run_row.task_family, run_row.task_type)
                    if run_row is not None
                    else None
                ),
                "status": item.status,
                "stage": None if workflow_row is None else workflow_row.stage,
                "createdAt": item.created_at.isoformat() if item.created_at is not None else None,
                "reviewer": item.metadata.get("reviewer"),
                "resolutionNote": item.metadata.get("resolution_note"),
            }
        )
    readiness_rows = [
        {
            "builder": builder_name,
            "ready": values["ready_runs"] > 0,
            "predictedRecords": values["predicted_records"],
            "blockers": sorted(values["blockers"])[:3],
        }
        for builder_name, values in sorted(readiness_accumulator.items())
    ]
    workflow_runs = [
        {
            "sessionId": row.session_id,
            "runId": row.run_id,
            "title": run_display_map.get(row.run_id, {}).get("title"),
            "summary": run_display_map.get(row.run_id, {}).get("summary"),
            "sessionTitle": session_display_map.get(row.session_id, {}).get("title"),
            "latestTimestamp": row.latest_timestamp,
            "evidenceLevel": row.evidence_level,
            "stage": row.stage,
            "stageLabel": row.stage_label,
            "stageDetail": row.stage_detail,
            "nextAction": row.next_action,
            "trajectoryStatus": row.trajectory_status,
            "reviewStatus": row.review_status,
            "feedbackCount": row.feedback_count,
            "qualityConfidence": row.quality_confidence,
            "verifierScore": row.verifier_score,
            "annotationArtifactId": row.annotation_artifact_id,
            "annotationProducer": row.annotation_producer,
            "annotationVersion": row.annotation_version,
            "supersedesArtifactId": row.supersedes_artifact_id,
            "sourceChannel": row.source_channel,
            "readyBuilders": list(row.ready_builders),
            "blockers": list(row.blockers),
            "reviewReasons": list(row.review_reasons),
        }
        for row in snapshot.workflow_runs
    ]

    total_runs = snapshot.overview.captured_runs
    request_total = sum(row.request_count for row in run_rows_by_id.values())
    run_success_total = sum(row.success_count for row in run_rows_by_id.values())
    declared_ratios = [run["declaredRatio"] for run in all_runs]
    anomaly_sessions = [session for session in sessions_payload if session["anomalies"]]
    feedback_open = [item for item in feedback_payloads if item["status"] in {"queued", "open"}]
    evaluation_asset_count = snapshot.overview.active_eval_suites

    overview_metrics = [
        {
            "label": "已接入会话",
            "value": str(snapshot.overview.captured_sessions),
            "change": f"最近 {len(sessions_payload)} 条",
            "tone": "accent",
        },
        {
            "label": "最近运行",
            "value": str(snapshot.overview.captured_runs),
            "change": f"请求 {request_total}",
            "tone": "info",
        },
        {
            "label": "可筛选运行",
            "value": format_percent(snapshot.overview.e1_ready_runs / total_runs if total_runs else 0),
            "change": f"{snapshot.overview.e1_ready_runs}/{total_runs}",
            "tone": "success",
        },
        {
            "label": "验证资产",
            "value": str(evaluation_asset_count),
            "change": f"决策证据齐全 {snapshot.overview.e2_ready_runs}/{total_runs}",
            "tone": "warning",
        },
        {
            "label": "可导出运行",
            "value": str(snapshot.overview.export_ready_runs),
            "change": f"{total_runs - snapshot.overview.export_ready_runs} 条受阻",
            "tone": "success",
        },
        {
            "label": "数据快照",
            "value": str(snapshot.overview.dataset_snapshots),
            "change": f"最近 {len(snapshot_payloads)} 份",
            "tone": "info",
        },
        {
            "label": "评测通过率",
            "value": format_percent(
                snapshot.overview.scorecards_pass
                / (
                    snapshot.overview.scorecards_pass
                    + snapshot.overview.scorecards_hold
                    + snapshot.overview.scorecards_fail
                )
                if (
                    snapshot.overview.scorecards_pass
                    + snapshot.overview.scorecards_hold
                    + snapshot.overview.scorecards_fail
                )
                else 0
            ),
            "change": (
                f"{snapshot.overview.scorecards_pass}/"
                f"{snapshot.overview.scorecards_pass + snapshot.overview.scorecards_hold + snapshot.overview.scorecards_fail}"
            ),
            "tone": "accent",
        },
    ]
    health_matrix = [
        {
            "label": "采集闭环",
            "score": format_percent(run_success_total / request_total if request_total else 0),
            "detail": f"最近 {len(sessions_payload)} 个会话的请求成功情况",
            "tone": "success",
        },
        {
            "label": "结构完整度",
            "score": format_percent(sum(declared_ratios) / len(declared_ratios) if declared_ratios else 0),
            "detail": "关键分支的显式声明程度与回放结构贴合度",
            "tone": "warning",
        },
        {
            "label": "标签覆盖",
            "score": format_percent(snapshot.overview.e1_ready_runs / total_runs if total_runs else 0),
            "detail": "按运行维度统计可进入筛选的标签覆盖",
            "tone": "info",
        },
        {
            "label": "导出准备度",
            "score": format_percent(snapshot.overview.export_ready_runs / total_runs if total_runs else 0),
            "detail": "至少一种学习型 builder 可导出的运行占比",
            "tone": "warning",
        },
    ]

    risks: list[dict[str, Any]] = []
    for item in feedback_open[:2]:
        risks.append(
            {
                "id": item["id"],
                "label": f"回流待处理：{item['sliceLabel']}",
                "detail": item["reason"],
                "href": "/feedback",
                "tone": "warning",
            }
        )
    for scorecard in scorecard_payloads:
        if scorecard["verdict"] != "pass":
            risks.append(
                {
                    "id": scorecard["id"],
                    "label": f"评分卡未通过：{scorecard['sliceLabel']}",
                    "detail": f"{scorecard['candidateModel']} vs {scorecard['baselineModel']}",
                    "href": "/evaluation",
                    "tone": "danger" if scorecard["verdict"] == "fail" else "warning",
                }
            )
    for session in anomaly_sessions[:1]:
        risks.append(
            {
                "id": f"risk:{session['id']}",
                "label": f"会话存在结构缺口：{session['id']}",
                "detail": session["anomalies"][0],
                "href": f"/sessions/{session['id']}",
                "tone": "warning",
            }
        )

    jobs = []
    for request in training_request_payloads[:2]:
        jobs.append(
            {
                "id": f"job:training:{request['id']}",
                "label": f"训练请求 {request['title']}",
                "status": request["status"],
                "detail": f"{request['recipeFamily']} · {request['datasetSnapshotTitle']}",
            }
        )
    for candidate in model_candidate_payloads[:2]:
        jobs.append(
            {
                "id": f"job:candidate:{candidate['id']}",
                "label": f"候选模型 {candidate['title']}",
                "status": "completed",
                "detail": candidate["summary"],
            }
        )
    for execution in eval_execution_payloads[:1]:
        jobs.append(
            {
                "id": f"job:evalexec:{execution['id']}",
                "label": f"评测执行 {execution['title']}",
                "status": "completed",
                "detail": execution["summary"],
            }
        )
    for snapshot_record in snapshot_payloads[:2]:
        jobs.append(
            {
                "id": f"job:snapshot:{snapshot_record['id']}",
                "label": f"导出快照 {snapshot_record['title']}",
                "status": "completed",
                "detail": f"{snapshot_record['builder']} · {snapshot_record['recordCount']} 条记录",
            }
        )
    for suite in eval_suite_payloads[:1]:
        jobs.append(
            {
                "id": f"job:eval:{suite['id']}",
                "label": f"验证套件 {suite['title']}",
                "status": "running" if suite["status"] == "active" else "completed",
                "detail": f"{suite['kind']} · {suite['items']} 个样本",
            }
        )
    for item in feedback_open[:1]:
        jobs.append(
            {
                "id": f"job:feedback:{item['id']}",
                "label": f"回流处理 {item['targetLabel']}",
                "status": "queued",
                "detail": item["reason"],
            }
        )

    latest_activity = max(
        (
            row.latest_timestamp
            for row in snapshot.recent_runs
            if row.latest_timestamp is not None
        ),
        default=None,
    )
    runs_with_identity = sum(1 for row in snapshot.recent_runs if row.task_instance_key is not None)
    runs_with_task_labels = sum(
        1
        for row in snapshot.recent_runs
        if row.task_family is not None and row.task_type is not None and row.task_instance_key is not None
    )
    runs_with_decision_signals = sum(
        1 for row in snapshot.recent_runs if row.semantic_event_count > 0
    )
    workflow_lanes = [
        {
            "id": "capture",
            "title": "1. 接入采集",
            "description": "确认真实请求已进入 proxy，并且运行能够正常闭合。",
            "count": snapshot.workflow_overview.in_progress_runs,
            "detail": "先看进行中的运行和 open span。",
            "href": "/access",
            "actionLabel": "检查实时采集",
            "tone": "info",
        },
        {
            "id": "annotate",
            "title": "2. 数据准备",
            "description": "自动补齐任务标签、质量判断和导出前检查。",
            "count": snapshot.workflow_overview.needs_annotation_runs,
            "detail": "没有稳定标签和清理结果的数据不会进入数据池。",
            "href": "/supervision",
            "actionLabel": "查看数据准备",
            "tone": "warning",
        },
        {
            "id": "review",
            "title": "3. 复核与筛选",
            "description": "低置信或回流样本进入人工复核，再决定是否入池。",
            "count": snapshot.workflow_overview.needs_review_runs,
            "detail": "judge 结果和人工 override 都保留可追溯版本链。",
            "href": "/feedback",
            "actionLabel": "处理复核队列",
            "tone": "accent",
        },
        {
            "id": "evaluate",
            "title": "4. 导出与验证",
            "description": "冻结数据批次，导出快照，并比较新旧模型效果。",
            "count": evaluation_asset_count,
            "detail": "已经生成的验证资产会直接出现在评测工作区。",
            "href": "/evaluation",
            "actionLabel": "查看验证资产",
            "tone": "success",
        },
    ]
    ingest_summary = {
        "sessionCount": snapshot.overview.captured_sessions,
        "runCount": snapshot.overview.captured_runs,
        "requestCount": request_total,
        "successRate": format_percent(run_success_total / request_total if request_total else 0),
        "inProgressRuns": snapshot.workflow_overview.in_progress_runs,
        "needsAnnotationRuns": snapshot.workflow_overview.needs_annotation_runs,
        "needsReviewRuns": snapshot.workflow_overview.needs_review_runs,
        "readyForDatasetRuns": snapshot.workflow_overview.ready_for_dataset_runs,
        "readyForEvalRuns": snapshot.workflow_overview.ready_for_eval_runs,
        "identityCoverage": format_percent(runs_with_identity / total_runs if total_runs else 0),
        "taskCoverage": format_percent(runs_with_task_labels / total_runs if total_runs else 0),
        "decisionCoverage": format_percent(
            runs_with_decision_signals / total_runs if total_runs else 0
        ),
        "semanticCoverage": format_percent(
            runs_with_decision_signals / total_runs if total_runs else 0
        ),
        "evaluationAssetCount": evaluation_asset_count,
        "latestActivity": format_datetime(latest_activity),
        "latestSessionId": sessions_payload[0]["id"] if sessions_payload else "-",
        "latestSessionTitle": sessions_payload[0].get("title") if sessions_payload else "-",
        "latestRunTitle": all_runs[0].get("title") if all_runs else "-",
    }

    return {
        "overviewMetrics": overview_metrics,
        "healthMatrix": health_matrix,
        "opportunities": opportunity_items[:3],
        "risks": risks[:3],
        "ingestSummary": ingest_summary,
        "workflowLanes": workflow_lanes,
        "workflowRuns": workflow_runs,
        "sessions": sessions_payload,
        "replayRecords": replay_payload[:run_limit],
        "artifacts": list(recent_artifact_map.values())[:artifact_limit],
        "slices": slices_payload,
        "candidates": candidate_payloads,
        "cohorts": cohort_payloads,
        "readinessRows": readiness_rows,
        "snapshots": snapshot_payloads,
        "evalSuites": eval_suite_payloads,
        "scorecards": scorecard_payloads,
        "coverageRows": coverage_rows,
        "coverageGuardrails": sorted(coverage_guardrails),
        "feedbackItems": feedback_payloads,
        "trainingRegistrySummary": training_registry_summary,
        "trainingRequests": training_request_payloads,
        "modelCandidates": model_candidate_payloads,
        "evalExecutions": eval_execution_payloads,
        "routerHandoffs": router_handoff_payloads,
        "jobs": jobs,
    }


def format_percent(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{round(float(value) * 100)}%"


def format_datetime(value: Any) -> str:
    if value is None:
        return "-"
    text = str(value)
    if "T" in text:
        text = text.replace("T", " ")
    return text[:16]


def format_latency(value: Any) -> str:
    if value is None:
        return "open"
    return f"{int(float(value))}ms"


def format_metric(metrics: dict[str, Any], *names: str) -> str:
    for name in names:
        value = metrics.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "latency" in name:
                return f"{int(float(value))}ms"
            if "cost" in name:
                return f"{float(value):.2f}x"
            if value <= 1.0:
                return format_percent(value)
            return str(round(float(value), 2))
    return "-"


def run_anomalies(
    *,
    run_title: str,
    run_row: DashboardRunRow,
    declared_ratio: float,
    request_summaries: list[Any],
) -> list[str]:
    anomalies: list[str] = []
    if any(summary.outcome == "open" for summary in request_summaries):
        anomalies.append(f"{run_title} 还有未闭合的请求")
    if run_row.task_instance_key is None:
        anomalies.append(f"{run_title} 还缺少稳定的任务实例标识")
    if declared_ratio < 0.5:
        anomalies.append(f"{run_title} 的关键分支仍主要依赖自动恢复")
    return anomalies


def fact_timeline_line(fact: Any) -> str:
    step = fact_timeline_step(fact)
    if step.get("detail"):
        return f"{step['label']} · {step['detail']}"
    return step["label"]


def complexity_for_sample_unit(sample_unit: str) -> str:
    return {
        "request": "low",
        "branch": "medium",
        "run": "high",
    }.get(sample_unit, "medium")


def strength_for_slice(slice_record: Any, scorecard_metrics: dict[str, Any] | None) -> str:
    if scorecard_metrics is not None:
        verifier_value = scorecard_metrics.get("verifier_pass_rate")
        if isinstance(verifier_value, (int, float)) and not isinstance(verifier_value, bool):
            return "strong" if float(verifier_value) >= 0.85 else "weak"
    return "strong" if slice_record.verifier_contract else "weak"


def rollout_for_decision(decision: Any | None) -> str:
    if decision is None:
        return "offline"
    stage = str(decision.stage or "offline")
    if decision.decision == "promote" and stage == "offline":
        return "canary"
    if decision.decision == "promote":
        return "expand"
    if decision.decision == "rollback":
        return "offline"
    return stage


def verdict_for_records(scorecard: Any | None, decision: Any | None) -> str:
    if decision is not None:
        return {
            "promote": "pass",
            "hold": "hold",
            "rollback": "fail",
        }.get(str(decision.decision), "hold")
    if scorecard is not None:
        return str(scorecard.verdict)
    return "hold"


def safe_actor(actor: Any) -> str:
    value = str(actor or "runtime")
    return value if value in {"model", "tool", "runtime"} else "runtime"


def _avg_latency_ms(request_summaries: list[Any]) -> float | None:
    values = [
        summary.total_latency_ms
        for summary in request_summaries
        if summary.total_latency_ms is not None
    ]
    if not values:
        return None
    return sum(int(value) for value in values) / len(values)


def _run_outcome(request_summaries: list[Any]) -> str:
    if any(summary.outcome == "failed" for summary in request_summaries):
        return "failed"
    if any(summary.outcome == "open" for summary in request_summaries):
        return "open"
    return "succeeded"


def humanize_identifier(value: str) -> str:
    normalized = value.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    if not normalized:
        return value
    return " ".join(part.capitalize() for part in normalized.split())


def task_label(task_family: str | None, task_type: str | None) -> str:
    parts = [
        humanize_identifier(value)
        for value in (task_family, task_type)
        if isinstance(value, str) and value
    ]
    return " / ".join(parts) if parts else "未命名任务"


def run_label(task_family: str | None, task_type: str | None, run_id: str | None) -> str:
    task_name = task_label(task_family, task_type)
    return task_name if run_id is None else f"{task_name} · {run_id}"


def active_run_annotation_payload(artifacts: list[Any]) -> dict[str, Any]:
    for artifact in artifacts:
        if artifact.status != "active":
            continue
        if artifact.artifact_type != "annotation":
            continue
        payload = artifact.payload if isinstance(artifact.payload, dict) else None
        if payload is None:
            continue
        if payload.get("annotation_kind") != "e1":
            continue
        return payload
    return {}


def describe_task_instance(
    *,
    task_instance_key: str | None,
    annotation_payload: dict[str, Any] | None = None,
) -> str | None:
    if not isinstance(task_instance_key, str) or not task_instance_key:
        return None
    repo = repo_name(task_instance_key=task_instance_key, annotation_payload=annotation_payload)
    issue = issue_number(task_instance_key)
    if repo and issue:
        return f"{repo} #{issue}"
    if repo:
        return repo
    return task_instance_key


def describe_run_title(
    *,
    task_family: str | None,
    task_type: str | None,
    task_instance_key: str | None,
    annotation_payload: dict[str, Any] | None = None,
) -> str:
    instance_label = describe_task_instance(
        task_instance_key=task_instance_key,
        annotation_payload=annotation_payload,
    )
    if instance_label:
        return instance_label
    return task_label(task_family, task_type)


def describe_run_summary(
    *,
    task_family: str | None,
    task_type: str | None,
    task_instance_key: str | None,
    annotation_payload: dict[str, Any] | None = None,
) -> str:
    task_name = task_label(task_family, task_type)
    repo = repo_name(task_instance_key=task_instance_key, annotation_payload=annotation_payload)
    if repo and task_instance_key:
        return f"{task_name} · 仓库 {repo} · 实例 {task_instance_key}"
    if task_instance_key:
        return f"{task_name} · 实例 {task_instance_key}"
    if repo:
        return f"{task_name} · 仓库 {repo}"
    return task_name


def describe_session_title(session_id: str, run_payloads: list[dict[str, Any]]) -> str:
    if not run_payloads:
        return humanize_identifier(session_id)
    primary = run_payloads[0].get("title")
    if isinstance(primary, str) and primary:
        if len(run_payloads) == 1:
            return primary
        return f"{primary} 等 {len(run_payloads)} 个运行"
    return humanize_identifier(session_id)


def describe_session_summary(*, run_count: int, request_count: int, branch_count: int) -> str:
    return f"{run_count} 个运行 · {request_count} 次请求 · {branch_count} 条分支"


def describe_branch_title(branch_type: str, source: str) -> str:
    branch_name = humanize_identifier(branch_type or "branch")
    source_label = "显式记录" if source == "declared" else "自动恢复"
    return f"{branch_name} · {source_label}"


def describe_branch_summary(
    *,
    branch_type: str,
    source: str,
    request_ids: list[str],
    parent_id: str | None,
) -> str:
    request_count = len(request_ids)
    parts = [
        "来自模型显式声明" if source == "declared" else "由执行轨迹自动恢复",
        f"覆盖 {request_count} 个请求步骤",
    ]
    if isinstance(parent_id, str) and parent_id:
        parts.append("与上游分支保持衔接")
    return " · ".join(parts)


def endpoint_step_type(path: str | None, actor: str) -> str:
    if actor == "model":
        return "模型推理"
    if actor == "tool":
        return "工具调用"
    if isinstance(path, str) and "semantic" in path:
        return "语义事件"
    return "运行时处理"


def endpoint_label(path: str | None, actor: str) -> str:
    if actor == "model":
        normalized = (path or "").rstrip("/")
        if normalized.endswith("/chat/completions") or normalized == "/chat/completions":
            return "对话推理"
        if normalized.endswith("/responses") or normalized == "/responses":
            return "响应生成"
        return "模型调用"
    if actor == "tool":
        return "工具调用"
    if isinstance(path, str) and "semantic" in path:
        return "语义事件"
    return humanize_identifier((path or "runtime").strip("/")) or "运行时"


def describe_request_summary(*, request_summary: Any, request_fact: Any | None) -> str:
    preview = request_preview(request_fact)
    if preview:
        return preview
    label = endpoint_label(getattr(request_summary, "path", None), safe_actor(getattr(request_summary, "actor", None)))
    outcome = getattr(request_summary, "outcome", None)
    if outcome == "failed":
        return f"{label}失败"
    if outcome == "open":
        return f"{label}仍在进行中"
    return f"{label}已完成"


def request_preview(request_fact: Any | None) -> str | None:
    if request_fact is None:
        return None
    payload_json = request_fact.payload.get("json")
    if isinstance(payload_json, dict):
        messages = payload_json.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                preview = message_preview(message)
                if preview:
                    return preview
        input_value = payload_json.get("input")
        if isinstance(input_value, str) and input_value.strip():
            return shorten_text(input_value)
    return None


def message_preview(message: Any) -> str | None:
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return shorten_text(content)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        if parts:
            return shorten_text(" ".join(parts))
    return None


def shorten_text(value: str, limit: int = 72) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 1]}…"


def repo_name(*, task_instance_key: str | None, annotation_payload: dict[str, Any] | None = None) -> str | None:
    if isinstance(annotation_payload, dict):
        repo = annotation_payload.get("repo")
        if isinstance(repo, str) and repo:
            return repo
    if isinstance(task_instance_key, str) and "__" in task_instance_key:
        return task_instance_key.split("__", 1)[0]
    return None


def issue_number(task_instance_key: str | None) -> str | None:
    if not isinstance(task_instance_key, str) or not task_instance_key:
        return None
    suffix = task_instance_key.split("__", 1)[-1]
    match = re.search(r"-(\d+)$", suffix)
    return match.group(1) if match else None


def fact_timeline_step(fact: Any) -> dict[str, str]:
    if fact.kind == "semantic_event":
        semantic_kind = fact.payload.get("semantic_kind")
        return {
            "label": semantic_event_label(semantic_kind if isinstance(semantic_kind, str) else None),
            "detail": "系统记录了一个关键决策节点",
        }
    path = fact.payload.get("path") if isinstance(fact.payload, dict) else None
    actor = safe_actor(getattr(fact, "actor", None))
    endpoint = endpoint_label(path if isinstance(path, str) else None, actor)
    preview = request_preview(fact if fact.kind == "request_started" else None)
    if fact.kind == "request_started":
        return {
            "label": f"{endpoint}开始",
            "detail": preview or "已发起一次新的步骤",
        }
    if fact.kind == "response_finished":
        return {
            "label": f"{endpoint}完成",
            "detail": response_detail(fact),
        }
    if fact.kind == "response_chunk":
        return {"label": f"{endpoint}流式返回", "detail": "正在持续返回结果"}
    return {
        "label": humanize_identifier(fact.kind),
        "detail": endpoint if endpoint else "执行事件",
    }


def response_detail(fact: Any) -> str:
    if not isinstance(fact.payload, dict):
        return "步骤已完成"
    status_code = fact.payload.get("status_code")
    if isinstance(status_code, int):
        return f"状态码 {status_code}"
    return "步骤已完成"


def semantic_event_label(semantic_kind: str | None) -> str:
    mapping = {
        "task_completed": "任务完成",
        "route_decided": "路由已决定",
        "retry_declared": "开始重试",
        "fallback_declared": "触发回退",
        "branch_opened": "分支已打开",
        "branch_closed": "分支已关闭",
    }
    if semantic_kind in mapping:
        return mapping[semantic_kind]
    if isinstance(semantic_kind, str) and semantic_kind:
        return humanize_identifier(semantic_kind)
    return "语义事件"


def build_snapshot_title(*, builder: str, cohort_name: str | None) -> str:
    builder_name = builder.upper() if builder else "DATASET"
    return f"{builder_name} · {cohort_name or '未命名批次'}"


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def describe_time_range(value: Any) -> str:
    if not isinstance(value, dict):
        return "时间范围待补充"
    start = value.get("start")
    end = value.get("end")
    if isinstance(start, str) and isinstance(end, str):
        return f"{format_datetime(start)} 到 {format_datetime(end)}"
    return "时间范围待补充"


def describe_selection_query(manifest: dict[str, Any]) -> str:
    selection_query = manifest.get("selection_query")
    if not isinstance(selection_query, dict):
        return "筛选规则待补充"
    task_family = selection_query.get("task_family")
    task_type = selection_query.get("task_type")
    source_channel = selection_query.get("source_channel")
    summary = task_label(
        task_family if isinstance(task_family, str) else None,
        task_type if isinstance(task_type, str) else None,
    )
    if isinstance(source_channel, str) and source_channel:
        return f"{summary} · 来源 {humanize_identifier(source_channel)}"
    return summary


def describe_quality_gate(value: Any) -> str:
    if not isinstance(value, dict):
        return "质量门槛待补充"
    quality = value.get("min_quality_confidence")
    verifier = value.get("min_verifier_score")
    parts: list[str] = []
    if isinstance(quality, (int, float)) and not isinstance(quality, bool):
        parts.append(f"质量 >= {float(quality):.2f}")
    if isinstance(verifier, (int, float)) and not isinstance(verifier, bool):
        parts.append(f"验证 >= {float(verifier):.2f}")
    return " · ".join(parts) if parts else "质量门槛待补充"


def describe_snapshot_split(manifest: dict[str, Any]) -> str:
    split = manifest.get("split")
    if not isinstance(split, dict):
        return "切分策略待补充"
    strategy = split.get("strategy")
    counts = split.get("counts")
    strategy_text = humanize_identifier(str(strategy)) if isinstance(strategy, str) and strategy else "切分策略"
    if isinstance(counts, dict):
        train = int(counts.get("train", 0))
        val = int(counts.get("val", 0))
        test = int(counts.get("test", 0))
        return f"{strategy_text} · train {train} / val {val} / test {test}"
    return strategy_text


def describe_cohort_contract(value: Any) -> str:
    if not isinstance(value, dict):
        return "未绑定批次约束"
    expected_use = value.get("expected_use")
    quality_gate = describe_quality_gate(value.get("quality_gate"))
    if isinstance(expected_use, str) and expected_use:
        return f"{humanize_identifier(expected_use)} · {quality_gate}"
    return quality_gate


def build_training_request_title(manifest: TrainingRequestManifest) -> str:
    dataset = manifest.dataset_snapshot_id or manifest.eval_suite_id or manifest.training_request_id
    return f"{manifest.recipe_family.upper()} · {dataset}"


def describe_training_request(manifest: TrainingRequestManifest) -> str:
    dataset = manifest.dataset_snapshot_id or "未绑定快照"
    return f"{manifest.base_model} · 数据快照 {dataset}"


def training_request_status(
    manifest: TrainingRequestManifest,
    candidate_entries: list[dict[str, Any]],
) -> str:
    if any(
        isinstance(item.get("manifest"), ModelCandidateManifest)
        and item["manifest"].training_request_id == manifest.training_request_id
        for item in candidate_entries
    ):
        return "completed"
    return "queued"


def build_candidate_title(manifest: ModelCandidateManifest) -> str:
    candidate_name = (
        manifest.candidate_model
        or manifest.published_model_path
        or manifest.sampler_path
        or manifest.checkpoint_path
        or manifest.candidate_model_id
    )
    return shorten_text(candidate_name, limit=48)


def describe_model_candidate(manifest: ModelCandidateManifest) -> str:
    dataset = manifest.dataset_snapshot_id or "未绑定快照"
    return f"{manifest.recipe_family.upper()} · 基座 {manifest.base_model} · 快照 {dataset}"


def build_eval_execution_title(manifest: EvalExecutionManifest) -> str:
    return f"{manifest.grader_name} · {manifest.case_count} 个样本"


def describe_eval_execution(manifest: EvalExecutionManifest) -> str:
    return f"验证套件 {manifest.eval_suite_id} · 候选 {manifest.candidate_model}"


def build_router_handoff_title(manifest: RouterHandoffManifest) -> str:
    return f"{manifest.stage} · {manifest.decision}"


def describe_router_handoff(manifest: RouterHandoffManifest) -> str:
    return f"{manifest.slice_id} · {manifest.candidate_model}"


def _manifest_sort_key(entry: dict[str, Any]) -> str:
    manifest = entry.get("manifest")
    created_at = getattr(manifest, "created_at", None)
    return str(created_at or "")


def _load_logits_manifest_inventory(manifest_dir: str | None) -> dict[str, list[dict[str, Any]]]:
    inventory = {
        "training_requests": [],
        "model_candidates": [],
        "eval_executions": [],
        "router_handoffs": [],
    }
    if not isinstance(manifest_dir, str) or not manifest_dir.strip():
        return inventory
    root = Path(manifest_dir).expanduser()
    if not root.exists():
        return inventory
    for path in root.rglob("*.json"):
        try:
            manifest = load_logits_manifest(path)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        entry = {"path": str(path), "manifest": manifest}
        if isinstance(manifest, TrainingRequestManifest):
            inventory["training_requests"].append(entry)
        elif isinstance(manifest, ModelCandidateManifest):
            inventory["model_candidates"].append(entry)
        elif isinstance(manifest, EvalExecutionManifest):
            inventory["eval_executions"].append(entry)
        elif isinstance(manifest, RouterHandoffManifest):
            inventory["router_handoffs"].append(entry)
    for key in inventory:
        inventory[key].sort(key=_manifest_sort_key, reverse=True)
    return inventory
