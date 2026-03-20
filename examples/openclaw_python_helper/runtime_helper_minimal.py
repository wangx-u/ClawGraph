from __future__ import annotations

import argparse
import json

from clawgraph import ClawGraphRuntimeClient, ClawGraphSession


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Minimal Python helper example for ClawGraph proxy integration."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--message", default="compare ART and AReaL")
    parser.add_argument("--tool-path", default="/tools/run")
    parser.add_argument("--tool-name", default="web_search")
    parser.add_argument("--tool-query", default="agent rl")
    parser.add_argument("--user-id")
    parser.add_argument("--thread-id")
    parser.add_argument("--task-id")
    parser.add_argument("--skip-tool", action="store_true")
    parser.add_argument("--skip-semantic", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    session = ClawGraphSession(
        user_id=args.user_id,
        thread_id=args.thread_id,
        task_id=args.task_id,
    )
    client = ClawGraphRuntimeClient(base_url=args.base_url, session=session)

    chat_response = client.chat_completions(
        {"messages": [{"role": "user", "content": args.message}]}
    )
    print("chat response:")
    print(json.dumps(chat_response.json(), ensure_ascii=True, indent=2, sort_keys=True))

    if not args.skip_tool:
        tool_response = client.tool(
            args.tool_path,
            {"tool": args.tool_name, "arguments": {"q": args.tool_query}},
        )
        print("tool response:")
        print(json.dumps(tool_response.json(), ensure_ascii=True, indent=2, sort_keys=True))

    if not args.skip_semantic:
        semantic_response = client.emit_semantic(
            kind="retry_declared",
            payload={
                "branch_id": "br_retry_example_1",
                "branch_type": "retry",
                "status": "succeeded",
            },
        )
        print("semantic response:")
        print(json.dumps(semantic_response.json(), ensure_ascii=True, indent=2, sort_keys=True))

    print("session context:")
    print(
        json.dumps(
            {
                "session_id": client.session.session_id,
                "run_id": client.session.run_id,
                "user_id": client.session.user_id,
                "thread_id": client.session.thread_id,
                "task_id": client.session.task_id,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
