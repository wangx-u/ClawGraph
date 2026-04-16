"""Evaluation bridge from Logits candidates back into ClawGraph scorecards."""

from __future__ import annotations

import asyncio
import inspect
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from clawgraph.evaluation import record_promotion_decision, record_scorecard
from clawgraph.export.dataset import build_records_for_builder
from clawgraph.integrations.logits._compat import import_logits_stack, load_dotted_object
from clawgraph.integrations.logits.manifests import (
    EvalExecutionManifest,
    ModelCandidateManifest,
    save_manifest,
)
from clawgraph.store import SQLiteFactStore


@dataclass(slots=True)
class EvalCase:
    """One normalized evaluation case derived from a frozen eval suite."""

    case_id: str
    prompt_messages: list[dict[str, Any]]
    reference_message: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def reference_text(self) -> str:
        content = self.reference_message.get("content")
        return content if isinstance(content, str) else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "prompt_messages": self.prompt_messages,
            "reference_message": self.reference_message,
            "metadata": self.metadata,
        }


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def exact_match_grader(case: EvalCase, candidate_text: str, reference_text: str) -> dict[str, Any]:
    matched = _normalize_text(candidate_text) == _normalize_text(reference_text)
    return {
        "pass": matched,
        "score": 1.0 if matched else 0.0,
    }


def contains_reference_grader(case: EvalCase, candidate_text: str, reference_text: str) -> dict[str, Any]:
    matched = _normalize_text(reference_text) in _normalize_text(candidate_text)
    return {
        "pass": matched,
        "score": 1.0 if matched else 0.0,
    }


_BUILTIN_GRADERS: dict[str, Callable[[EvalCase, str, str], dict[str, Any]]] = {
    "exact-match": exact_match_grader,
    "contains-reference": contains_reference_grader,
}


def load_builtin_grader(name: str) -> Callable[[EvalCase, str, str], dict[str, Any]]:
    grader = _BUILTIN_GRADERS.get(name)
    if grader is None:
        raise ValueError(f"unsupported builtin grader: {name}")
    return grader


def load_eval_cases_for_suite(
    *,
    store_uri: str,
    eval_suite_id: str,
) -> tuple[Any, list[EvalCase]]:
    """Load one eval suite and normalize its cases from the frozen cohort."""

    store = SQLiteFactStore(store_uri)
    suite = store.get_eval_suite(eval_suite_id)
    if suite is None:
        raise ValueError(f"eval suite not found: {eval_suite_id}")
    if suite.cohort_id is None:
        raise ValueError(f"eval suite {eval_suite_id} has no cohort source")
    members = store.list_cohort_members(suite.cohort_id, slice_id=suite.slice_id)
    if not members:
        raise ValueError(f"eval suite {eval_suite_id} has no cohort members")
    facts = []
    artifacts = []
    seen_artifact_ids: set[str] = set()
    for member in members:
        facts.extend(store.list_facts(run_id=member.run_id))
        for artifact in store.list_artifacts(
            session_id=member.session_id,
            run_id=member.run_id,
            latest_only=True,
        ):
            if artifact.artifact_id in seen_artifact_ids:
                continue
            artifacts.append(artifact)
            seen_artifact_ids.add(artifact.artifact_id)
    if not facts:
        raise ValueError(f"eval suite {eval_suite_id} produced no facts")
    facts.sort(key=lambda fact: (fact.timestamp, fact.fact_id))
    records = build_records_for_builder(
        builder="sft",
        facts=facts,
        artifacts=artifacts,
    )
    cases: list[EvalCase] = []
    for index, row in enumerate(records, start=1):
        prompt = row.get("prompt")
        completion = row.get("completion")
        if not isinstance(prompt, list) or not isinstance(completion, dict):
            continue
        case_id = (
            row.get("request_fact_id")
            or row.get("request_id")
            or row.get("response_fact_id")
            or f"case_{index}"
        )
        cases.append(
            EvalCase(
                case_id=str(case_id),
                prompt_messages=prompt,
                reference_message=completion,
                metadata={
                    "run_id": row.get("run_id"),
                    "session_id": row.get("session_id"),
                    "slice_id": row.get("slice_id"),
                    "task_family": row.get("task_family"),
                    "task_type": row.get("task_type"),
                    "task_instance_key": row.get("task_instance_key"),
                },
            )
        )
    if not cases:
        raise ValueError(f"eval suite {eval_suite_id} produced no normalized cases")
    return suite, cases


def evaluate_candidate_on_suite(
    *,
    store_uri: str,
    eval_suite_id: str,
    candidate_manifest: ModelCandidateManifest,
    baseline_model: str,
    baseline_model_path: str | None = None,
    grader_name: str = "exact-match",
    grader_ref: str | None = None,
    thresholds: dict[str, Any] | None = None,
    max_tokens: int = 512,
    temperature: float = 0.0,
    top_p: float = 1.0,
    base_url: str | None = None,
    sample_fn: Callable[[dict[str, Any], EvalCase], Any] | None = None,
    scorecard_metadata: dict[str, Any] | None = None,
    record_promotion: bool = False,
    promotion_stage: str = "offline",
    coverage_policy_version: str = "logits.eval.v1",
    promotion_summary: str | None = None,
    rollback_conditions: list[str] | None = None,
    output_path: Path | None = None,
) -> tuple[EvalExecutionManifest, Any, Any | None]:
    """Run one candidate against a frozen eval suite, then write back scorecard and promotion."""

    suite, cases = load_eval_cases_for_suite(store_uri=store_uri, eval_suite_id=eval_suite_id)
    grader = load_builtin_grader(grader_name)
    if grader_ref is not None:
        loaded_grader = load_dotted_object(grader_ref)
        if not callable(loaded_grader):
            raise ValueError(f"grader_ref is not callable: {grader_ref}")
        grader = loaded_grader
        grader_name = grader_ref

    if sample_fn is None:
        sample_fn = _build_builtin_sampler(
            candidate_manifest=candidate_manifest,
            baseline_model=baseline_model,
            baseline_model_path=baseline_model_path,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            base_url=base_url,
        )

    candidate_descriptor = {
        "label": "candidate",
        "model": candidate_manifest.candidate_model or candidate_manifest.candidate_model_id,
        "model_path": candidate_manifest.sampler_path or candidate_manifest.checkpoint_path,
        "base_model": candidate_manifest.base_model,
        "renderer_name": candidate_manifest.renderer_name,
    }
    baseline_descriptor = {
        "label": "baseline",
        "model": baseline_model,
        "model_path": baseline_model_path,
        "base_model": baseline_model,
        "renderer_name": candidate_manifest.renderer_name,
    }

    case_results: list[dict[str, Any]] = []
    candidate_passes = 0
    baseline_passes = 0
    candidate_scores: list[float] = []
    baseline_scores: list[float] = []
    candidate_latencies: list[float] = []
    baseline_latencies: list[float] = []
    for case in cases:
        candidate_sample = _normalize_sample_result(sample_fn(candidate_descriptor, case))
        baseline_sample = _normalize_sample_result(sample_fn(baseline_descriptor, case))
        candidate_grade = _normalize_grade_result(
            grader(case, candidate_sample["text"], case.reference_text)
        )
        baseline_grade = _normalize_grade_result(
            grader(case, baseline_sample["text"], case.reference_text)
        )
        if candidate_grade["pass"]:
            candidate_passes += 1
        if baseline_grade["pass"]:
            baseline_passes += 1
        candidate_scores.append(candidate_grade["score"])
        baseline_scores.append(baseline_grade["score"])
        if candidate_sample["latency_ms"] is not None:
            candidate_latencies.append(candidate_sample["latency_ms"])
        if baseline_sample["latency_ms"] is not None:
            baseline_latencies.append(baseline_sample["latency_ms"])
        case_results.append(
            {
                "case_id": case.case_id,
                "reference_text": case.reference_text,
                "candidate": {
                    "text": candidate_sample["text"],
                    "pass": candidate_grade["pass"],
                    "score": candidate_grade["score"],
                    "latency_ms": candidate_sample["latency_ms"],
                    "details": candidate_grade["details"],
                },
                "baseline": {
                    "text": baseline_sample["text"],
                    "pass": baseline_grade["pass"],
                    "score": baseline_grade["score"],
                    "latency_ms": baseline_sample["latency_ms"],
                    "details": baseline_grade["details"],
                },
                "metadata": case.metadata,
            }
        )

    total_cases = len(cases)
    metrics = {
        "task_success_rate": candidate_passes / total_cases,
        "baseline_task_success_rate": baseline_passes / total_cases,
        "avg_score": sum(candidate_scores) / total_cases,
        "baseline_avg_score": sum(baseline_scores) / total_cases,
        "relative_win_rate": sum(
            1 for c_score, b_score in zip(candidate_scores, baseline_scores, strict=True) if c_score >= b_score
        )
        / total_cases,
    }
    if candidate_latencies:
        metrics["p95_latency_ms"] = _percentile(candidate_latencies, 95)
    if baseline_latencies:
        metrics["baseline_p95_latency_ms"] = _percentile(baseline_latencies, 95)

    resolved_thresholds = dict(thresholds or {})
    if not resolved_thresholds:
        resolved_thresholds = {
            "task_success_rate": {"op": "gte", "value": metrics["baseline_task_success_rate"]},
            "avg_score": {"op": "gte", "value": metrics["baseline_avg_score"]},
        }
        if "baseline_p95_latency_ms" in metrics:
            resolved_thresholds["p95_latency_ms"] = {
                "op": "lte",
                "value": metrics["baseline_p95_latency_ms"],
            }

    scorecard = record_scorecard(
        store_uri=store_uri,
        eval_suite_id=eval_suite_id,
        candidate_model=candidate_manifest.candidate_model
        or candidate_manifest.sampler_path
        or candidate_manifest.checkpoint_path
        or candidate_manifest.candidate_model_id,
        baseline_model=baseline_model,
        metrics=metrics,
        thresholds=resolved_thresholds,
        metadata={
            "candidate_model_id": candidate_manifest.candidate_model_id,
            "candidate_model_path": candidate_manifest.sampler_path or candidate_manifest.checkpoint_path,
            "baseline_model_path": baseline_model_path,
            "grader_name": grader_name,
            "case_count": total_cases,
            **(scorecard_metadata or {}),
        },
    )
    promotion = None
    if record_promotion:
        promotion = record_promotion_decision(
            store_uri=store_uri,
            scorecard_id=scorecard.scorecard_id,
            stage=promotion_stage,
            coverage_policy_version=coverage_policy_version,
            summary=promotion_summary
            or f"Candidate {candidate_manifest.candidate_model_id} evaluated on {eval_suite_id}",
            rollback_conditions=rollback_conditions or [],
        )

    manifest = EvalExecutionManifest(
        eval_suite_id=eval_suite_id,
        candidate_model_id=candidate_manifest.candidate_model_id,
        candidate_model=candidate_manifest.candidate_model
        or candidate_manifest.sampler_path
        or candidate_manifest.checkpoint_path
        or candidate_manifest.candidate_model_id,
        candidate_model_path=candidate_manifest.sampler_path or candidate_manifest.checkpoint_path,
        baseline_model=baseline_model,
        baseline_model_path=baseline_model_path,
        grader_name=grader_name,
        case_count=total_cases,
        metrics=metrics,
        thresholds=resolved_thresholds,
        scorecard_id=scorecard.scorecard_id,
        promotion_decision_id=None if promotion is None else promotion.promotion_decision_id,
        metadata={
            "eval_suite_name": suite.name,
            "slice_id": suite.slice_id,
            "case_results": case_results[:10],
        },
    )
    if output_path is not None:
        save_manifest(manifest, output_path)
    return manifest, scorecard, promotion


def _normalize_sample_result(raw: Any) -> dict[str, Any]:
    if inspect.isawaitable(raw):
        raw = asyncio.run(raw)
    if isinstance(raw, str):
        return {"text": raw, "latency_ms": None, "metadata": {}}
    if isinstance(raw, dict):
        text = raw.get("text")
        if not isinstance(text, str):
            raise ValueError("sample result dict must contain a string text field")
        latency_ms = raw.get("latency_ms")
        if latency_ms is not None and not isinstance(latency_ms, (int, float)):
            raise ValueError("latency_ms must be numeric when provided")
        return {
            "text": text,
            "latency_ms": None if latency_ms is None else float(latency_ms),
            "metadata": raw.get("metadata", {}),
        }
    raise ValueError("sample_fn must return a string or a dict")


def _normalize_grade_result(raw: Any) -> dict[str, Any]:
    if inspect.isawaitable(raw):
        raw = asyncio.run(raw)
    if isinstance(raw, bool):
        return {"pass": raw, "score": 1.0 if raw else 0.0, "details": {}}
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        score = float(raw)
        return {"pass": score > 0.0, "score": score, "details": {}}
    if isinstance(raw, dict):
        passed = raw.get("pass")
        score = raw.get("score")
        if not isinstance(passed, bool):
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                passed = float(score) > 0.0
            else:
                raise ValueError("grader dict result must include pass or numeric score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            score = 1.0 if passed else 0.0
        return {
            "pass": passed,
            "score": float(score),
            "details": {
                key: value
                for key, value in raw.items()
                if key not in {"pass", "score"}
            },
        }
    raise ValueError("grader must return bool, number, or dict")


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _build_builtin_sampler(
    *,
    candidate_manifest: ModelCandidateManifest,
    baseline_model: str,
    baseline_model_path: str | None,
    max_tokens: int,
    temperature: float,
    top_p: float,
    base_url: str | None,
) -> Callable[[dict[str, Any], EvalCase], dict[str, Any]]:
    import_logits_stack()
    import logits
    from logits_cookbook import client_utils, renderers
    from logits_cookbook.tokenizer_utils import get_tokenizer

    renderer_name = candidate_manifest.renderer_name
    if renderer_name is None:
        raise ValueError("candidate manifest must provide renderer_name for builtin evaluation")
    tokenizer = get_tokenizer(candidate_manifest.base_model or baseline_model)
    renderer = renderers.get_renderer(renderer_name, tokenizer)
    service_client = client_utils.create_service_client(base_url=base_url)
    candidate_sampler = service_client.create_sampling_client(
        model_path=candidate_manifest.sampler_path or candidate_manifest.checkpoint_path,
        base_model=candidate_manifest.base_model,
    )
    baseline_kwargs: dict[str, Any]
    if baseline_model_path:
        baseline_kwargs = {
            "model_path": baseline_model_path,
            "base_model": baseline_model,
        }
    else:
        baseline_kwargs = {"base_model": baseline_model}
    baseline_sampler = service_client.create_sampling_client(**baseline_kwargs)

    async def _sample_with_sampler(
        sampler: Any,
        case: EvalCase,
    ) -> dict[str, Any]:
        prompt = renderer.build_generation_prompt(case.prompt_messages)
        sampling_params = logits.types.SamplingParams(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=renderer.get_stop_sequences(),
        )
        start = time.perf_counter()
        response = await sampler.sample_async(
            prompt=prompt,
            num_samples=1,
            sampling_params=sampling_params,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0
        message, _ = renderer.parse_response(response.sequences[0].tokens)
        text = renderers.get_text_content(message)
        return {
            "text": text,
            "latency_ms": latency_ms,
        }

    def _sample(model_descriptor: dict[str, Any], case: EvalCase) -> dict[str, Any]:
        sampler = candidate_sampler if model_descriptor["label"] == "candidate" else baseline_sampler
        return asyncio.run(_sample_with_sampler(sampler, case))

    return _sample
