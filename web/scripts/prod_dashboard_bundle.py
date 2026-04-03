#!/usr/bin/env python3
"""Build one ClawGraph dashboard bundle directly from a local sqlite store."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from clawgraph.curation import list_slice_candidates  # noqa: E402
from clawgraph.export.readiness import build_dataset_readiness_summary  # noqa: E402
from clawgraph.graph.inspect import (  # noqa: E402
    build_branch_inspect_summaries,
    build_request_span_summaries,
    build_session_inspect_summary,
)
from clawgraph.query import ClawGraphQueryService  # noqa: E402
from clawgraph.store import SQLiteFactStore  # noqa: E402


def normalize_store_uri(store_uri: str) -> str:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--session-limit", type=int, default=12)
    parser.add_argument("--run-limit", type=int, default=24)
    parser.add_argument("--artifact-limit", type=int, default=40)
    return parser.parse_args()


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


def evidence_rank(level: str) -> int:
    return {"E0": 0, "E1": 1, "E2": 2}.get(level, 0)


def combine_evidence(levels: list[str]) -> str:
    if not levels:
        return "E0"
    return min(levels, key=evidence_rank)


def derive_evidence_level(readiness_summary: Any) -> str:
    evidence = readiness_summary.evidence
    if evidence.get("level") == "E1" and any(builder.ready for builder in readiness_summary.builders):
        return "E2"
    return str(evidence.get("level") or "E0")


def run_anomalies(
    *,
    run_id: str,
    readiness_summary: Any,
    declared_ratio: float,
    request_summaries: list[Any],
) -> list[str]:
    anomalies: list[str] = []
    run_evidence = readiness_summary.evidence.get("runs", {}).get(run_id, {})
    missing_fields = run_evidence.get("missing_fields", [])

    if any(summary.outcome == "open" for summary in request_summaries):
        anomalies.append(f"{run_id} 存在 open span")
    if "task_instance_key" in missing_fields:
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


def main() -> int:
    args = parse_args()
    store = SQLiteFactStore(normalize_store_uri(args.store))
    service = ClawGraphQueryService(store=store)

    session_ids = list(store.iter_sessions())[: args.session_limit]
    all_runs: list[dict[str, Any]] = []
    sessions_payload: list[dict[str, Any]] = []
    replay_payload: list[dict[str, Any]] = []
    recent_artifact_map: dict[str, dict[str, Any]] = {}
    builder_accumulator: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"ready_runs": 0, "predicted_records": 0, "blockers": set()}
    )

    for session_id in session_ids:
        facts = store.list_facts(session_id=session_id)
        artifacts = store.list_artifacts(session_id=session_id, latest_only=True)
        session_summary = build_session_inspect_summary(facts, artifacts)
        run_ids = list(store.iter_runs(session_id=session_id))
        run_payloads: list[dict[str, Any]] = []
        session_anomalies: list[str] = []
        run_evidence_levels: list[str] = []

        for artifact in artifacts:
            recent_artifact_map[artifact.artifact_id] = {
                "id": artifact.artifact_id,
                "type": artifact.artifact_type,
                "targetRef": artifact.target_ref,
                "producer": artifact.producer,
                "status": artifact.status,
                "confidence": "-" if artifact.confidence is None else f"{artifact.confidence:.2f}",
                "version": artifact.version or "-"
            }

        for run_id in run_ids:
            run_facts = store.list_facts(run_id=run_id)
            run_artifacts = store.list_artifacts(session_id=session_id, run_id=run_id, latest_only=True)
            request_summaries = build_request_span_summaries(run_facts, run_artifacts)
            branch_summaries = build_branch_inspect_summaries(run_facts, run_artifacts)
            readiness_summary = build_dataset_readiness_summary(run_facts, run_artifacts)
            declared_count = sum(1 for branch in branch_summaries if branch.source == "declared")
            declared_ratio = declared_count / len(branch_summaries) if branch_summaries else 1.0
            run_level = derive_evidence_level(readiness_summary)
            run_anomaly_list = run_anomalies(
                run_id=run_id,
                readiness_summary=readiness_summary,
                declared_ratio=declared_ratio,
                request_summaries=request_summaries,
            )
            outcome = (
                "failed"
                if any(summary.outcome == "failed" for summary in request_summaries)
                else "open"
                if any(summary.outcome == "open" for summary in request_summaries)
                else "succeeded"
            )
            avg_latency_values = [
                summary.total_latency_ms
                for summary in request_summaries
                if summary.total_latency_ms is not None
            ]
            avg_latency_ms = (
                sum(int(value) for value in avg_latency_values) / len(avg_latency_values)
                if avg_latency_values
                else None
            )

            for builder in readiness_summary.builders:
                builder_accumulator[builder.builder]["predicted_records"] += builder.predicted_records
                builder_accumulator[builder.builder]["ready_runs"] += 1 if builder.ready else 0
                for blocker in builder.blockers:
                    builder_accumulator[builder.builder]["blockers"].add(blocker)

            run_payload = {
                "id": run_id,
                "requestCount": len(request_summaries),
                "successCount": sum(1 for summary in request_summaries if summary.outcome == "succeeded"),
                "failureCount": sum(1 for summary in request_summaries if summary.outcome == "failed"),
                "openCount": sum(1 for summary in request_summaries if summary.outcome == "open"),
                "branchCount": len(branch_summaries),
                "declaredRatio": round(declared_ratio, 3),
                "artifactCount": len(run_artifacts),
                "evidenceLevel": run_level,
                "avgLatency": format_latency(avg_latency_ms),
                "outcome": outcome,
            }
            run_payloads.append(run_payload)
            run_evidence_levels.append(run_level)
            session_anomalies.extend(run_anomaly_list)
            all_runs.append(run_payload)

            replay_payload.append(
                {
                    "sessionId": session_id,
                    "runId": run_id,
                    "outcome": outcome,
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

        sessions_payload.append(
            {
                "id": session_id,
                "userIds": session_summary.user_ids,
                "runs": run_payloads,
                "requests": session_summary.request_count,
                "branches": session_summary.branch_count,
                "evidenceLevel": combine_evidence(run_evidence_levels),
                "anomalies": list(dict.fromkeys(session_anomalies))[:4],
            }
        )

    slices = service.list_slices()
    cohorts = service.list_cohorts()
    cohort_payloads: list[dict[str, Any]] = []
    holdout_run_ids: set[str] = set()
    snapshots = service.list_dataset_snapshots()
    eval_suites = service.list_eval_suites()
    scorecards = service.list_scorecards()
    decisions = service.list_promotion_decisions()
    feedback_items = service.list_feedback_queue()

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
            _, candidates = list_slice_candidates(
                store=store,
                slice_id=slice_record.slice_id,
                limit=24,
            )
        except ValueError:
            continue

        for candidate in candidates:
            status = "eligible"
            if candidate.run_id in holdout_run_ids:
                status = "holdout"
            elif candidate.quality_confidence < 0.8 or candidate.verifier_score < 0.8:
                status = "review"
            candidate_payloads.append(
                {
                    "runId": candidate.run_id,
                    "taskInstanceKey": candidate.task_instance_key,
                    "templateHash": candidate.task_template_hash,
                    "quality": round(candidate.quality_confidence, 4),
                    "verifier": round(candidate.verifier_score, 4),
                    "source": candidate.source_channel,
                    "clusterId": candidate.metadata.get("cluster_keys", {}).get("task_template", candidate.task_template_hash),
                    "status": status,
                }
            )

    snapshot_payloads = [
        {
            "id": snapshot.dataset_snapshot_id,
            "builder": snapshot.builder,
            "sampleUnit": snapshot.sample_unit,
            "cohortId": snapshot.cohort_id or "-",
            "recordCount": snapshot.record_count,
            "outputPath": snapshot.output_path or "-",
            "createdAt": format_datetime(snapshot.created_at),
        }
        for snapshot in snapshots
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
        slice_scorecard = next((scorecard for scorecard in scorecards if scorecard.slice_id == slice_record.slice_id), None)
        slice_decision = next((decision for decision in decisions if decision.slice_id == slice_record.slice_id), None)
        verdict = verdict_for_records(slice_scorecard, slice_decision)
        rollout = rollout_for_decision(slice_decision)
        recipe_builders = sorted(
            {
                snapshot.builder
                for snapshot in snapshots
                if snapshot.cohort_id is not None
                and any(cohort.cohort_id == snapshot.cohort_id and slice_record.slice_id in cohort.slice_ids for cohort in cohorts)
            }
        )
        recipe = " + ".join(recipe_builders[:2]) if recipe_builders else "sft"
        candidate_count = sum(1 for candidate in candidate_payloads if candidate["taskInstanceKey"] and candidate["source"] and candidate["runId"])
        opportunity = "阻塞"
        if verdict == "pass" and slice_record.risk_level != "high":
            opportunity = "高"
        elif verdict in {"pass", "hold"}:
            opportunity = "中"
        coverage_rows.append(
            {
                "sliceId": slice_record.slice_id,
                "verifier": strength_for_slice(slice_record, None if slice_scorecard is None else slice_scorecard.metrics),
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
        for builder_name, values in sorted(builder_accumulator.items())
    ]

    total_runs = len(all_runs)
    request_total = sum(session["requests"] for session in sessions_payload)
    run_success_total = sum(run["requestCount"] - run["failureCount"] - run["openCount"] for run in all_runs)
    exportable_runs = sum(
        1
        for run in all_runs
        if run["evidenceLevel"] == "E2" or any(
            row["ready"] and row["predictedRecords"] > 0 for row in readiness_rows
        )
    )
    e1_runs = sum(1 for run in all_runs if evidence_rank(run["evidenceLevel"]) >= 1)
    e2_runs = sum(1 for run in all_runs if run["evidenceLevel"] == "E2")
    pass_scorecards = sum(1 for scorecard in scorecard_payloads if scorecard["verdict"] == "pass")
    declared_ratios = [run["declaredRatio"] for run in all_runs]
    anomaly_sessions = [session for session in sessions_payload if session["anomalies"]]
    feedback_open = [item for item in feedback_payloads if item["status"] in {"queued", "open"}]

    overview_metrics = [
        {"label": "采集会话", "value": str(len(sessions_payload)), "change": f"最近 {len(sessions_payload)} 条", "tone": "accent"},
        {"label": "采集运行", "value": str(total_runs), "change": f"请求 {request_total}", "tone": "info"},
        {"label": "E1 就绪率", "value": format_percent(e1_runs / total_runs if total_runs else 0), "change": f"{e1_runs}/{total_runs}", "tone": "success"},
        {"label": "E2 就绪率", "value": format_percent(e2_runs / total_runs if total_runs else 0), "change": f"{e2_runs}/{total_runs}", "tone": "warning"},
        {"label": "可导出运行", "value": str(exportable_runs), "change": f"{total_runs - exportable_runs} 条受阻", "tone": "success"},
        {"label": "数据快照", "value": str(len(snapshot_payloads)), "change": f"最近 {len(snapshot_payloads)} 份", "tone": "info"},
        {
            "label": "评测通过率",
            "value": format_percent(pass_scorecards / len(scorecard_payloads) if scorecard_payloads else 0),
            "change": f"{pass_scorecards}/{len(scorecard_payloads)}",
            "tone": "accent",
        },
    ]

    health_matrix = [
        {
            "label": "采集健康度",
            "score": format_percent(run_success_total / request_total if request_total else 0),
            "detail": f"最近 {len(sessions_payload)} 个会话的请求成功情况",
            "tone": "success",
        },
        {
            "label": "分支保真度",
            "score": format_percent(sum(declared_ratios) / len(declared_ratios) if declared_ratios else 0),
            "detail": "Declared branch 与实际回放结构的贴合度",
            "tone": "warning",
        },
        {
            "label": "监督覆盖率",
            "score": format_percent(e1_runs / total_runs if total_runs else 0),
            "detail": "按运行维度统计 E1/E2 证据覆盖",
            "tone": "info",
        },
        {
            "label": "数据集就绪度",
            "score": format_percent(exportable_runs / total_runs if total_runs else 0),
            "detail": "至少一种 builder 可导出的运行占比",
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
    for snapshot in snapshot_payloads[:2]:
        jobs.append(
            {
                "id": f"job:snapshot:{snapshot['id']}",
                "label": f"导出快照 {snapshot['id']}",
                "status": "completed",
                "detail": f"{snapshot['builder']} · {snapshot['recordCount']} 条记录",
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

    bundle = {
        "overviewMetrics": overview_metrics,
        "healthMatrix": health_matrix,
        "opportunities": opportunity_items[:3],
        "risks": risks[:3],
        "sessions": sessions_payload,
        "replayRecords": replay_payload[: args.run_limit],
        "artifacts": list(recent_artifact_map.values())[: args.artifact_limit],
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

    sys.stdout.write(json.dumps(bundle, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
