"""Web-dashboard bundle builders backed by shared ClawGraph read models."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from clawgraph.curation import list_slice_candidates
from clawgraph.dashboard import DashboardRunRow, build_dashboard_snapshot
from clawgraph.export import build_dataset_readiness_summary
from clawgraph.graph import (
    build_branch_inspect_summaries,
    build_request_span_summaries,
    build_session_inspect_summary,
)
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
    readiness_accumulator: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"ready_runs": 0, "predicted_records": 0, "blockers": set()}
    )
    all_runs: list[dict[str, Any]] = []

    for session_id in session_ids:
        facts = resolved_store.list_facts(session_id=session_id)
        if not facts:
            continue
        artifacts = resolved_store.list_artifacts(session_id=session_id, latest_only=True)
        session_summary = build_session_inspect_summary(facts, artifacts)
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
            request_summaries = build_request_span_summaries(run_facts, run_artifacts)
            branch_summaries = build_branch_inspect_summaries(run_facts, run_artifacts)
            readiness_summary = build_dataset_readiness_summary(run_facts, run_artifacts)
            declared_count = sum(1 for branch in branch_summaries if branch.source == "declared")
            declared_ratio = declared_count / len(branch_summaries) if branch_summaries else 1.0
            run_row = run_rows_by_id.get(run_id)
            if run_row is None:
                raise ValueError(f"dashboard snapshot missing run row: {run_id}")
            workflow_row = workflow_rows_by_id.get(run_id)
            if workflow_row is None:
                raise ValueError(f"dashboard snapshot missing workflow row: {run_id}")

            run_payload = {
                "id": run_id,
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
            run_payloads.append(run_payload)
            all_runs.append(run_payload)
            session_anomalies.extend(
                run_anomalies(
                    run_id=run_id,
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

            replay_payload.append(
                {
                    "sessionId": session_id,
                    "runId": run_id,
                    "outcome": run_payload["outcome"],
                    "timeline": [fact_timeline_line(fact) for fact in run_facts[:18]],
                    "branches": [
                        {
                            "id": branch.branch_id,
                            "type": branch.branch_type,
                            "status": branch.status,
                            "source": branch.source,
                            "parentId": branch.parent_branch_id,
                            "requestIds": branch.request_ids,
                        }
                        for branch in branch_summaries
                    ],
                    "requests": [
                        {
                            "id": summary.request_id,
                            "actor": safe_actor(summary.actor),
                            "path": summary.path,
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
        sessions_payload.append(
            {
                "id": session_id,
                "userIds": session_summary.user_ids,
                "runs": run_payloads,
                "requests": session_summary.request_count,
                "branches": session_summary.branch_count,
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
        review_queue = cohort.manifest.get("review")
        review_count = len(review_queue) if isinstance(review_queue, list) else 0
        if purpose == "评测":
            holdout_run_ids.update(member.run_id for member in members)
        cohort_payloads.append(
            {
                "id": cohort.cohort_id,
                "name": cohort.name,
                "purpose": purpose,
                "sliceIds": cohort.slice_ids,
                "selectedCount": len(members),
                "holdoutCount": holdout_count,
                "reviewCount": review_count,
            }
        )

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
                }
            )

    snapshot_payloads = [
        {
            "id": snapshot_record.dataset_snapshot_id,
            "builder": snapshot_record.builder,
            "sampleUnit": snapshot_record.sample_unit,
            "cohortId": snapshot_record.cohort_id or "-",
            "recordCount": snapshot_record.record_count,
            "outputPath": snapshot_record.output_path or "-",
            "createdAt": format_datetime(snapshot_record.created_at),
        }
        for snapshot_record in snapshots
    ]
    eval_suite_payloads = [
        {
            "id": suite.eval_suite_id,
            "sliceId": suite.slice_id,
            "kind": suite.suite_kind,
            "cohortId": suite.cohort_id or "-",
            "status": suite.status,
            "items": int(
                suite.manifest.get("task_instance_count")
                or suite.manifest.get("run_count")
                or suite.manifest.get("session_count")
                or 0
            ),
        }
        for suite in eval_suites
    ]
    scorecard_payloads = [
        {
            "id": scorecard.scorecard_id,
            "evalSuiteId": scorecard.eval_suite_id,
            "sliceId": scorecard.slice_id,
            "candidateModel": scorecard.candidate_model,
            "baselineModel": scorecard.baseline_model,
            "verdict": scorecard.verdict,
            "successRate": format_metric(scorecard.metrics, "task_success_rate", "success_rate"),
            "verifierRate": format_metric(scorecard.metrics, "verifier_pass_rate", "verifier_rate"),
            "p95Latency": format_metric(scorecard.metrics, "p95_latency", "p95_latency_ms"),
            "cost": format_metric(scorecard.metrics, "cost_ratio", "unit_cost"),
            "fallbackRate": format_metric(scorecard.metrics, "fallback_rate"),
        }
        for scorecard in scorecards
    ]
    slices_payload = [
        {
            "id": slice_record.slice_id,
            "taskFamily": slice_record.task_family,
            "taskType": slice_record.task_type,
            "taxonomyVersion": slice_record.taxonomy_version,
            "sampleUnit": slice_record.sample_unit,
            "verifierContract": slice_record.verifier_contract,
            "risk": slice_record.risk_level,
            "defaultUse": slice_record.default_use,
            "owner": slice_record.owner,
        }
        for slice_record in slices
    ]

    coverage_rows: list[dict[str, Any]] = []
    opportunity_items: list[dict[str, Any]] = []
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
        rollout = rollout_for_decision(slice_decision)
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
                "verifier": strength_for_slice(
                    slice_record,
                    None if slice_scorecard is None else slice_scorecard.metrics,
                ),
                "risk": slice_record.risk_level,
                "complexity": complexity_for_sample_unit(slice_record.sample_unit),
                "recipe": recipe,
                "modelBand": slice_scorecard.candidate_model if slice_scorecard is not None else "待配置",
                "verdict": verdict,
                "rollout": rollout,
            }
        )
        opportunity_items.append(
            {
                "sliceId": slice_record.slice_id,
                "opportunity": opportunity,
                "reason": f"scorecard={verdict}，risk={slice_record.risk_level}，候选池可见",
                "href": "/coverage",
                "tone": "success" if opportunity == "高" else "warning" if opportunity == "中" else "danger",
            }
        )

    feedback_payloads = [
        {
            "id": item.feedback_id,
            "source": item.source,
            "targetRef": item.target_ref,
            "reason": item.reason,
            "sliceId": item.slice_id,
            "status": item.status,
            "createdAt": item.created_at.isoformat() if item.created_at is not None else None,
            "reviewer": item.metadata.get("reviewer"),
            "resolutionNote": item.metadata.get("resolution_note"),
        }
        for item in feedback_items
    ]
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
            "label": "可评估运行",
            "value": format_percent(snapshot.overview.e2_ready_runs / total_runs if total_runs else 0),
            "change": f"{snapshot.overview.e2_ready_runs}/{total_runs}",
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
                "label": f"回流待处理：{item['sliceId']}",
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
                    "label": f"评分卡未通过：{scorecard['sliceId']}",
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
    for snapshot_record in snapshot_payloads[:2]:
        jobs.append(
            {
                "id": f"job:snapshot:{snapshot_record['id']}",
                "label": f"导出快照 {snapshot_record['id']}",
                "status": "completed",
                "detail": f"{snapshot_record['builder']} · {snapshot_record['recordCount']} 条记录",
            }
        )
    for suite in eval_suite_payloads[:1]:
        jobs.append(
            {
                "id": f"job:eval:{suite['id']}",
                "label": f"评测套件 {suite['id']}",
                "status": "running" if suite["status"] == "active" else "completed",
                "detail": f"{suite['kind']} · {suite['items']} 个样本",
            }
        )
    for item in feedback_open[:1]:
        jobs.append(
            {
                "id": f"job:feedback:{item['id']}",
                "label": f"回流处理 {item['id']}",
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
    runs_with_semantics = sum(1 for row in snapshot.recent_runs if row.semantic_event_count > 0)
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
            "count": snapshot.workflow_overview.ready_for_eval_runs,
            "detail": "准备好的运行可以直接进入数据导出和验证流程。",
            "href": "/datasets",
            "actionLabel": "查看导出",
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
        "semanticCoverage": format_percent(runs_with_semantics / total_runs if total_runs else 0),
        "latestActivity": format_datetime(latest_activity),
        "latestSessionId": sessions_payload[0]["id"] if sessions_payload else "-",
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
        "feedbackItems": feedback_payloads,
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
    run_id: str,
    run_row: DashboardRunRow,
    declared_ratio: float,
    request_summaries: list[Any],
) -> list[str]:
    anomalies: list[str] = []
    if any(summary.outcome == "open" for summary in request_summaries):
        anomalies.append(f"{run_id} 存在 open span")
    if run_row.task_instance_key is None:
        anomalies.append(f"{run_id} 缺少 task_instance_key")
    if declared_ratio < 0.5:
        anomalies.append(f"{run_id} 的 declared branch 覆盖率偏低")
    return anomalies


def fact_timeline_line(fact: Any) -> str:
    if fact.kind == "semantic_event":
        semantic_kind = fact.payload.get("semantic_kind")
        if isinstance(semantic_kind, str) and semantic_kind:
            return semantic_kind
    path = fact.payload.get("path")
    if isinstance(path, str) and path:
        return f"{fact.kind} · {path}"
    return fact.kind


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
