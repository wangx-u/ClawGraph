#!/usr/bin/env python3
"""Run one Agent Diff task through a model behind ClawGraph proxy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _ensure_agent_diff_python_sdk() -> None:
    sdk_root = (
        _workspace_root() / "agent-diff" / "sdk" / "agent-diff-python"
    ).resolve()
    if sdk_root.exists() and str(sdk_root) not in sys.path:
        sys.path.insert(0, str(sdk_root))


_ensure_agent_diff_python_sdk()

from openai import OpenAI

from clawgraph.protocol.factories import new_artifact_record
from clawgraph.runtime.openai import ClawGraphOpenAIClient
from clawgraph.runtime.client import ClawGraphSession
from clawgraph.store import SQLiteFactStore

from agent_diff import AgentDiff, BashExecutorProxy


SUPPORTED_ENDPOINT_HINTS = {
    "slack": [
        "https://slack.com/api/conversations.list",
        "https://slack.com/api/chat.postMessage",
        "https://slack.com/api/conversations.history",
    ],
    "linear": [
        "https://api.linear.app/graphql",
    ],
    "box": [
        "https://api.box.com/2.0/search",
        "https://api.box.com/2.0/files",
    ],
    "calendar": [
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
    ],
    "github": [
        "https://api.github.com/user",
        "https://api.github.com/repos",
        "https://api.github.com/repos/{owner}/{repo}/pulls",
        "https://api.github.com/repos/{owner}/{repo}/issues",
    ],
}


@dataclass(slots=True)
class DemoOutcome:
    suite_id: str
    suite_name: str
    test_id: str
    test_name: str
    service: str
    environment_id: str
    agent_diff_run_id: str
    clawgraph_session_id: str
    clawgraph_run_id: str
    passed: bool
    score_value: float
    final_text: str
    diff_summary: dict[str, int]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one Agent Diff benchmark task through a model behind ClawGraph proxy."
    )
    parser.add_argument("--agent-diff-base-url", default=os.getenv("AGENT_DIFF_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--agent-diff-api-key", default=os.getenv("AGENT_DIFF_API_KEY"))
    parser.add_argument("--suite-name", default="Slack Bench")
    parser.add_argument("--test-id")
    parser.add_argument("--test-name")
    parser.add_argument("--test-index", type=int, default=0)
    parser.add_argument("--proxy-base-url", default=os.getenv("CLAWGRAPH_PROXY_BASE_URL", "http://127.0.0.1:8093/v1"))
    parser.add_argument("--proxy-api-key", default=os.getenv("CLAWGRAPH_PROXY_API_KEY", "clawgraph-local"))
    parser.add_argument("--model", default=os.getenv("AGENT_DIFF_DEMO_MODEL", "deepseek-chat"))
    parser.add_argument("--store", default=os.getenv("CLAWGRAPH_STORE_URI", "sqlite:////tmp/clawgraph-agent-diff-demo.db"))
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1500)
    parser.add_argument("--producer", default="agent-diff-demo")
    parser.add_argument("--task-family", default="enterprise_api_workflow")
    parser.add_argument("--taxonomy-version", default="agent-diff.v1")
    parser.add_argument("--source-channel", default="agent_diff_demo")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--skip-artifacts", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def _resolve_suite_and_test(client: AgentDiff, *, suite_name: str, test_id: str | None, test_name: str | None, test_index: int) -> tuple[Any, Any]:
    suites = client.list_test_suites(name=suite_name)
    matched = [suite for suite in suites.testSuites if suite.name == suite_name]
    if not matched:
        raise ValueError(f"no test suite found with name: {suite_name}")
    suite = client.get_test_suite(matched[0].id, expand=True)
    tests = suite.tests
    if test_id:
        filtered = [test for test in tests if str(test.id) == test_id]
        if not filtered:
            raise ValueError(f"no test found with id: {test_id}")
        return suite, filtered[0]
    if test_name:
        filtered = [test for test in tests if test.name == test_name]
        if not filtered:
            raise ValueError(f"no test found with name: {test_name}")
        return suite, filtered[0]
    if test_index < 0 or test_index >= len(tests):
        raise ValueError(f"test-index out of range: {test_index}")
    return suite, tests[test_index]


def _service_instruction(service: str) -> str:
    hints = SUPPORTED_ENDPOINT_HINTS.get(service, [])
    endpoint_block = "\n".join(f"- {item}" for item in hints) if hints else "- Use the service replica endpoints documented by Agent Diff."
    service_notes = {
        "github": (
            "For GitHub tasks, first discover the target repository, pull request, or issue with GET requests. "
            "Do not assume the repo name; inspect the replica state before mutating it."
        ),
        "box": (
            "For Box tasks, verify folder and file ids before move or rename operations, and re-read the destination "
            "state after each mutation."
        ),
        "calendar": (
            "For Calendar tasks, list calendars and events before creating or deleting items, and verify the final "
            "calendar state rather than relying on your own summary."
        ),
    }
    extra_note = service_notes.get(service, "Verify each important mutation with a follow-up read before you claim completion.")
    return (
        f"You are solving one Agent Diff task against the {service} API replica.\n"
        "You must use the execute_bash tool to inspect or mutate the environment.\n"
        "Do not claim success unless the tool output confirms the action happened.\n"
        "Keep commands short, explicit, and directly tied to the task.\n"
        "Useful endpoints include:\n"
        f"{endpoint_block}\n"
        f"{extra_note}\n"
        "Authentication is already injected by Agent Diff. Use real service URLs; they will be routed automatically."
    )


def _tool_schema() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "execute_bash",
                "description": "Execute bash commands, usually curl requests against the Agent Diff replica APIs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Bash command to execute.",
                        }
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            },
        }
    ]


def _assistant_message_for_history(message: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "assistant",
    }
    if getattr(message, "content", None):
        payload["content"] = message.content
    tool_calls = []
    for tool_call in getattr(message, "tool_calls", None) or []:
        tool_calls.append(
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
        )
    if tool_calls:
        payload["tool_calls"] = tool_calls
    elif "content" not in payload:
        payload["content"] = ""
    return payload


def _run_openai_tool_loop(
    *,
    wrapped_client: ClawGraphOpenAIClient,
    model: str,
    test_prompt: str,
    service: str,
    executor: BashExecutorProxy,
    max_steps: int,
    temperature: float,
    max_tokens: int,
) -> str:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _service_instruction(service)},
        {"role": "user", "content": test_prompt},
    ]
    final_text = ""
    tool_spec = _tool_schema()
    for _ in range(max_steps):
        response = wrapped_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tool_spec,
            tool_choice="auto",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        message = response.choices[0].message
        messages.append(_assistant_message_for_history(message))
        if getattr(message, "content", None):
            final_text = message.content
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            break
        for tool_call in tool_calls:
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {"command": tool_call.function.arguments}
            command = arguments.get("command")
            if not isinstance(command, str) or not command.strip():
                result: dict[str, Any] = {
                    "status": "error",
                    "stderr": "tool call missing command",
                    "stdout": "",
                }
            else:
                result = executor.execute(command)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    return final_text


def _normalize_score(raw_score: Any, passed: bool) -> float:
    if isinstance(raw_score, dict):
        for key in ("percent", "score", "value"):
            value = raw_score.get(key)
            if isinstance(value, (int, float)):
                if key == "percent":
                    return max(0.0, min(float(value) / 100.0, 1.0))
                return max(0.0, min(float(value), 1.0))
    if isinstance(raw_score, (int, float)):
        return max(0.0, min(float(raw_score), 1.0))
    return 1.0 if passed else 0.0


def _diff_summary(diff_payload: Any) -> dict[str, int]:
    if not isinstance(diff_payload, dict):
        return {"inserts": 0, "updates": 0, "deletes": 0}
    summary: dict[str, int] = {}
    for key in ("inserts", "updates", "deletes"):
        value = diff_payload.get(key)
        summary[key] = len(value) if isinstance(value, list) else 0
    return summary


def _wait_for_clawgraph_facts(store: SQLiteFactStore, *, run_id: str, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if store.list_facts(run_id=run_id):
            return
        time.sleep(0.2)


def _append_demo_artifacts(
    *,
    store_uri: str,
    producer: str,
    task_family: str,
    taxonomy_version: str,
    source_channel: str,
    suite: Any,
    test: Any,
    outcome: DemoOutcome,
    prompt: str,
) -> list[str]:
    store = SQLiteFactStore(store_uri)
    _wait_for_clawgraph_facts(store, run_id=outcome.clawgraph_run_id, timeout_seconds=5.0)
    task_template_hash = hashlib.sha1(
        f"{suite.id}:{test.id}:{test.name}".encode("utf-8")
    ).hexdigest()[:12]
    task_type = f"{outcome.service}_api_workflow"
    task_instance_key = f"agent-diff:{test.id}"
    annotation = new_artifact_record(
        artifact_type="annotation",
        target_ref=f"run:{outcome.clawgraph_run_id}",
        producer=producer,
        payload={
            "annotation_kind": "e1",
            "task_family": task_family,
            "task_type": task_type,
            "task_template_hash": task_template_hash,
            "task_instance_key": task_instance_key,
            "verifier_name": "agent-diff",
            "verifier_score": outcome.score_value,
            "quality_confidence": 1.0,
            "taxonomy_version": taxonomy_version,
            "annotation_version": "agent-diff.e1.v1",
            "source_channel": source_channel,
            "suite_id": str(suite.id),
            "suite_name": suite.name,
            "test_id": str(test.id),
            "test_name": test.name,
            "service": outcome.service,
        },
        session_id=outcome.clawgraph_session_id,
        run_id=outcome.clawgraph_run_id,
        confidence=1.0,
        metadata={
            "prompt": prompt,
            "environment_id": outcome.environment_id,
            "agent_diff_run_id": outcome.agent_diff_run_id,
        },
    )
    score = new_artifact_record(
        artifact_type="score",
        target_ref=f"run:{outcome.clawgraph_run_id}",
        producer="agent-diff",
        payload={
            "score": outcome.score_value,
            "passed": outcome.passed,
            "suite_id": str(suite.id),
            "suite_name": suite.name,
            "test_id": str(test.id),
            "test_name": test.name,
            "service": outcome.service,
            "diff_summary": outcome.diff_summary,
        },
        session_id=outcome.clawgraph_session_id,
        run_id=outcome.clawgraph_run_id,
        confidence=1.0,
        metadata={
            "environment_id": outcome.environment_id,
            "agent_diff_run_id": outcome.agent_diff_run_id,
        },
    )
    store.append_artifacts([annotation, score])
    return [annotation.artifact_id, score.artifact_id]


def _print_human(outcome: DemoOutcome, artifact_ids: list[str] | None) -> None:
    print(f"Suite: {outcome.suite_name} ({outcome.suite_id})")
    print(f"Test: {outcome.test_name} ({outcome.test_id})")
    print(f"Service: {outcome.service}")
    print(f"AgentDiff environment: {outcome.environment_id}")
    print(f"AgentDiff run: {outcome.agent_diff_run_id}")
    print(f"ClawGraph session: {outcome.clawgraph_session_id}")
    print(f"ClawGraph run: {outcome.clawgraph_run_id}")
    print(f"Passed: {outcome.passed}")
    print(f"Score: {outcome.score_value:.3f}")
    print(f"Diff summary: {json.dumps(outcome.diff_summary, ensure_ascii=False)}")
    if artifact_ids:
        print(f"Artifacts: {', '.join(artifact_ids)}")
    print("Final response:")
    print(outcome.final_text or "(empty)")


def main() -> int:
    args = _build_arg_parser().parse_args()
    client = AgentDiff(
        api_key=args.agent_diff_api_key,
        base_url=args.agent_diff_base_url,
    )
    suite, test = _resolve_suite_and_test(
        client,
        suite_name=args.suite_name,
        test_id=args.test_id,
        test_name=args.test_name,
        test_index=args.test_index,
    )

    env = client.init_env(testId=test.id)
    wrapped: ClawGraphOpenAIClient | None = None
    try:
        run = client.start_run(envId=env.environmentId, testId=test.id)
        executor = BashExecutorProxy(
            env.environmentId,
            base_url=client.base_url,
            api_key=client.api_key,
        )
        openai_client = OpenAI(
            api_key=args.proxy_api_key,
            base_url=args.proxy_base_url,
        )
        session = ClawGraphSession(
            user_id="agent-diff-demo",
            thread_id=env.environmentId,
            task_id=str(test.id),
        )
        wrapped = ClawGraphOpenAIClient(openai_client, session=session)
        wrapped.start_new_run()
        final_text = _run_openai_tool_loop(
            wrapped_client=wrapped,
            model=args.model,
            test_prompt=test.prompt,
            service=env.service,
            executor=executor,
            max_steps=args.max_steps,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        eval_result = client.evaluate_run(runId=run.runId)
        diff_result = client.diff_run(runId=run.runId)
        score_value = _normalize_score(eval_result.score, eval_result.passed)
        outcome = DemoOutcome(
            suite_id=str(suite.id),
            suite_name=suite.name,
            test_id=str(test.id),
            test_name=test.name,
            service=env.service,
            environment_id=env.environmentId,
            agent_diff_run_id=run.runId,
            clawgraph_session_id=wrapped.session.session_id or "",
            clawgraph_run_id=wrapped.session.run_id or "",
            passed=bool(eval_result.passed),
            score_value=score_value,
            final_text=final_text,
            diff_summary=_diff_summary(diff_result.diff),
        )
        artifact_ids: list[str] | None = None
        if not args.skip_artifacts:
            artifact_ids = _append_demo_artifacts(
                store_uri=args.store,
                producer=args.producer,
                task_family=args.task_family,
                taxonomy_version=args.taxonomy_version,
                source_channel=args.source_channel,
                suite=suite,
                test=test,
                outcome=outcome,
                prompt=test.prompt,
            )
        payload = {
            "suite_id": outcome.suite_id,
            "suite_name": outcome.suite_name,
            "test_id": outcome.test_id,
            "test_name": outcome.test_name,
            "service": outcome.service,
            "environment_id": outcome.environment_id,
            "agent_diff_run_id": outcome.agent_diff_run_id,
            "clawgraph_session_id": outcome.clawgraph_session_id,
            "clawgraph_run_id": outcome.clawgraph_run_id,
            "passed": outcome.passed,
            "score": outcome.score_value,
            "diff_summary": outcome.diff_summary,
            "artifacts": artifact_ids or [],
            "final_text": outcome.final_text,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _print_human(outcome, artifact_ids)
        return 0
    finally:
        try:
            client.delete_env(env.environmentId)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
