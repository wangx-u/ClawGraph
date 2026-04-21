#!/usr/bin/env python3
"""Collect multiple Agent Diff runs and turn them into a Logits-ready SFT request."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_PACKS: dict[str, list[dict[str, Any]]] = {
    "slack-stable": [
        {
            "suite_name": "Slack Bench",
            "test_index": 0,
            "label": "send-general-message",
        },
        {
            "suite_name": "Slack Bench",
            "test_index": 3,
            "label": "create-channel",
        },
        {
            "suite_name": "Slack Bench",
            "test_index": 7,
            "label": "archive-channel",
        },
        {
            "suite_name": "Slack Bench",
            "test_index": 12,
            "label": "update-topic",
        },
        {
            "suite_name": "Slack Bench",
            "test_index": 15,
            "label": "multi-channel-send",
        },
    ],
    "cross-service-stable": [
        {
            "suite_name": "Slack Bench",
            "test_index": 15,
            "label": "slack-multi-channel-send",
            "max_steps": 12,
            "max_tokens": 1800,
        },
        {
            "suite_name": "Linear Bench",
            "test_index": 9,
            "label": "linear-create-multiple-issues",
            "max_steps": 14,
            "max_tokens": 1800,
        },
    ],
    "cross-service-debug": [
        {
            "suite_name": "Slack Bench",
            "test_index": 15,
            "label": "slack-multi-channel-send",
            "max_steps": 12,
            "max_tokens": 1800,
        },
        {
            "suite_name": "Linear Bench",
            "test_index": 9,
            "label": "linear-create-multiple-issues",
            "max_steps": 14,
            "max_tokens": 1800,
        },
        {
            "suite_name": "Calendar Bench",
            "test_index": 1,
            "label": "calendar-multi-step-organization",
            "max_steps": 20,
            "max_tokens": 1800,
        },
        {
            "suite_name": "Box Bench v2",
            "test_index": 10,
            "label": "box-nested-folders",
            "max_steps": 16,
            "max_tokens": 1800,
        },
        {
            "suite_name": "GitHub Bench",
            "test_index": 0,
            "label": "github-request-reviewers",
            "max_steps": 14,
            "max_tokens": 1800,
        },
    ],
}


@dataclass(slots=True)
class DemoRun:
    index: int
    suite_name: str
    label: str
    payload: dict[str, Any]


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_python() -> str:
    return sys.executable


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a stable Agent Diff pack, freeze a slice-level cohort, and prepare a Logits SFT request."
    )
    parser.add_argument("--python-bin", default=_default_python())
    parser.add_argument("--pack", default="slack-stable", choices=sorted(DEFAULT_PACKS))
    parser.add_argument("--store", default="sqlite:////tmp/clawgraph-agent-diff-logits-demo.db")
    parser.add_argument("--proxy-base-url", default="http://127.0.0.1:8094/v1")
    parser.add_argument("--proxy-api-key", default="clawgraph-local")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--base-model", default="meta-llama/Llama-3.2-1B-Instruct")
    parser.add_argument("--min-successful-runs", type=int, default=4)
    parser.add_argument("--min-score", type=float, default=0.8)
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--phase2-output-dir", type=Path, default=Path("/tmp/clawgraph-agent-diff-logits-phase2"))
    parser.add_argument("--logits-output-dir", type=Path, default=Path("/tmp/clawgraph-agent-diff-logits-train"))
    parser.add_argument("--cohort-name", default="agent-diff-slack-sft")
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def _run_json(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"command did not return JSON: {' '.join(command)}\nstdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}"
        ) from exc


def _run_demo(
    *,
    python_bin: str,
    spec: dict[str, Any],
    store: str,
    proxy_base_url: str,
    proxy_api_key: str,
    model: str,
) -> dict[str, Any]:
    script = (_workspace_root() / "clawgraph" / "benchmarks" / "agent_diff" / "run_agent_diff_demo.py").resolve()
    command = [
        python_bin,
        str(script),
        "--json",
        "--store",
        store,
        "--proxy-base-url",
        proxy_base_url,
        "--proxy-api-key",
        proxy_api_key,
        "--model",
        model,
        "--suite-name",
        spec["suite_name"],
    ]
    if "max_steps" in spec:
        command.extend(["--max-steps", str(spec["max_steps"])])
    if "max_tokens" in spec:
        command.extend(["--max-tokens", str(spec["max_tokens"])])
    if "temperature" in spec:
        command.extend(["--temperature", str(spec["temperature"])])
    if "test_index" in spec:
        command.extend(["--test-index", str(spec["test_index"])])
    if "test_id" in spec:
        command.extend(["--test-id", str(spec["test_id"])])
    if "test_name" in spec:
        command.extend(["--test-name", str(spec["test_name"])])
    return _run_json(command, cwd=(_workspace_root() / "clawgraph"))


def _run_phase2(
    *,
    python_bin: str,
    store: str,
    representative: dict[str, Any],
    output_dir: Path,
    cohort_name: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        python_bin,
        "-m",
        "clawgraph.cli.main",
        "phase2",
        "run",
        "--store",
        store,
        "--session",
        representative["clawgraph_session_id"],
        "--run-id",
        representative["clawgraph_run_id"],
        "--selection-scope",
        "slice",
        "--builder",
        "sft",
        "--output-dir",
        str(output_dir),
        "--cohort-name",
        cohort_name,
        "--json",
    ]
    return _run_json(command, cwd=(_workspace_root() / "clawgraph"))


def _first_dataset_snapshot_id(phase2_payload: dict[str, Any]) -> str:
    for item in phase2_payload.get("exports", []):
        snapshot = item.get("dataset_snapshot") or {}
        dataset_snapshot_id = snapshot.get("dataset_snapshot_id")
        if dataset_snapshot_id:
            return dataset_snapshot_id
    raise ValueError("phase2 payload did not include a dataset snapshot id")


def _run_prepare_sft(
    *,
    python_bin: str,
    store: str,
    dataset_snapshot_id: str,
    output_dir: Path,
    base_model: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        python_bin,
        "-m",
        "clawgraph.cli.main",
        "logits",
        "prepare-sft",
        "--store",
        store,
        "--dataset-snapshot-id",
        dataset_snapshot_id,
        "--output-dir",
        str(output_dir),
        "--base-model",
        base_model,
        "--json",
    ]
    return _run_json(command, cwd=(_workspace_root() / "clawgraph"))


def _find_training_manifest(output_dir: Path) -> str | None:
    matches = sorted(output_dir.glob("*.sft.request.json"))
    if not matches:
        return None
    return str(matches[-1])


def _render_text(summary: dict[str, Any]) -> str:
    lines = [
        f"Pack: {summary['pack']}",
        f"Successful runs: {summary['successful_runs']} / {summary['attempted_runs']}",
        f"Store: {summary['store']}",
        f"Dataset snapshot: {summary['dataset_snapshot_id']}",
        f"Slice: {summary['slice_id']}",
        f"Cohort: {summary['training_cohort_id']}",
        f"Logits request: {summary['training_request_id']}",
        f"Logits dataset: {summary['logits_input_path']}",
        f"Manifest: {summary['training_manifest_path']}",
    ]
    return "\n".join(lines)


def main() -> int:
    args = _parser().parse_args()
    pack = DEFAULT_PACKS[args.pack]
    runs: list[DemoRun] = []
    successful: list[DemoRun] = []

    for index, spec in enumerate(pack):
        payload = _run_demo(
            python_bin=args.python_bin,
            spec=spec,
            store=args.store,
            proxy_base_url=args.proxy_base_url,
            proxy_api_key=args.proxy_api_key,
            model=args.model,
        )
        run = DemoRun(
            index=index,
            suite_name=spec["suite_name"],
            label=spec.get("label", f"case-{index}"),
            payload=payload,
        )
        runs.append(run)
        if payload.get("passed") and float(payload.get("score", 0.0)) >= args.min_score:
            successful.append(run)
        if not args.run_all and len(successful) >= args.min_successful_runs:
            break

    if len(successful) < args.min_successful_runs:
        raise SystemExit(
            f"only collected {len(successful)} successful runs; need at least {args.min_successful_runs}"
        )

    representative = successful[0].payload
    phase2_payload = _run_phase2(
        python_bin=args.python_bin,
        store=args.store,
        representative=representative,
        output_dir=args.phase2_output_dir,
        cohort_name=args.cohort_name,
    )
    dataset_snapshot_id = _first_dataset_snapshot_id(phase2_payload)
    logits_payload = _run_prepare_sft(
        python_bin=args.python_bin,
        store=args.store,
        dataset_snapshot_id=dataset_snapshot_id,
        output_dir=args.logits_output_dir,
        base_model=args.base_model,
    )

    training_request_id = logits_payload.get("training_request_id") or logits_payload.get("trainingRequestId")
    manifest_path = (
        logits_payload.get("manifest_path")
        or logits_payload.get("manifestPath")
        or _find_training_manifest(args.logits_output_dir)
    )
    input_path = logits_payload.get("input_path") or logits_payload.get("inputPath")
    training_cohort = phase2_payload.get("training_cohort") or {}
    slice_payload = phase2_payload.get("slice") or {}
    slice_record = slice_payload.get("record") or {}

    summary = {
        "pack": args.pack,
        "attempted_runs": len(runs),
        "successful_runs": len(successful),
        "store": args.store,
        "results": [
            {
                "label": run.label,
                "suite_name": run.suite_name,
                "test_name": run.payload.get("test_name"),
                "service": run.payload.get("service"),
                "passed": run.payload.get("passed"),
                "score": run.payload.get("score"),
                "clawgraph_session_id": run.payload.get("clawgraph_session_id"),
                "clawgraph_run_id": run.payload.get("clawgraph_run_id"),
            }
            for run in runs
        ],
        "dataset_snapshot_id": dataset_snapshot_id,
        "slice_id": slice_record.get("slice_id"),
        "training_cohort_id": training_cohort.get("cohort_id"),
        "phase2_output_dir": str(args.phase2_output_dir.resolve()),
        "logits_output_dir": str(args.logits_output_dir.resolve()),
        "training_request_id": training_request_id,
        "training_manifest_path": manifest_path,
        "logits_input_path": input_path,
        "phase2": phase2_payload,
        "logits": logits_payload,
    }

    if args.summary_out is not None:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(_render_text(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
