from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from clawgraph.artifacts import plan_artifact_bootstrap
from clawgraph.export import build_dataset_readiness_summary, export_dataset
from clawgraph.graph import build_session_inspect_summary, render_session_replay
from clawgraph.proxy import ProxyConfig
from clawgraph.proxy.server import _build_handler
from clawgraph.store import SQLiteFactStore


def _post_json(
    url: str,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urlopen(request) as response:
            return response.getcode(), response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def _start_server(handler_cls: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _make_retry_then_stream_handler() -> type[BaseHTTPRequestHandler]:
    class RetryThenStreamHandler(BaseHTTPRequestHandler):
        call_count = 0
        lock = threading.Lock()

        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            request_json = json.loads(body.decode("utf-8"))
            with type(self).lock:
                type(self).call_count += 1
                call_count = type(self).call_count

            if call_count == 1:
                response_body = json.dumps({"error": "upstream failed"}).encode("utf-8")
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for token in ("Repo A ", "focuses on proxy-first RL capture."):
                chunk = (
                    'data: {"choices":[{"delta":{"role":"assistant","content":"'
                    + token
                    + '"}}]}\n\n'
                ).encode("utf-8")
                self.wfile.write(chunk)
                self.wfile.flush()
            if request_json.get("stream"):
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    return RetryThenStreamHandler


def _make_responses_stream_handler() -> type[BaseHTTPRequestHandler]:
    class ResponsesStreamHandler(BaseHTTPRequestHandler):
        last_path: str | None = None

        def do_POST(self) -> None:  # noqa: N802
            type(self).last_path = self.path
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            events = [
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {
                        "id": "msg_1",
                        "type": "message",
                        "role": "assistant",
                    },
                },
                {
                    "type": "response.output_text.delta",
                    "item_id": "msg_1",
                    "delta": "Need to call search first.",
                },
                {
                    "type": "response.output_item.added",
                    "output_index": 1,
                    "item": {
                        "id": "fc_1",
                        "type": "function_call",
                        "name": "web_search",
                        "call_id": "call_1",
                    },
                },
                {
                    "type": "response.function_call_arguments.delta",
                    "item_id": "fc_1",
                    "delta": '{"q":"agent rl"}',
                },
            ]
            for event in events:
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    return ResponsesStreamHandler


class RuntimeIntegrationTest(unittest.TestCase):
    def test_multi_actor_session_replay_inspect_and_export_consistency(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "multi_actor_sft.jsonl"
            store_uri = f"sqlite:///{db_path}"

            class ModelHandler(BaseHTTPRequestHandler):
                call_count = 0

                def do_POST(self) -> None:  # noqa: N802
                    body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    request_json = json.loads(body.decode("utf-8"))
                    type(self).call_count += 1

                    if type(self).call_count == 1:
                        response_body = json.dumps(
                            {
                                "choices": [
                                    {
                                        "message": {
                                            "role": "assistant",
                                            "tool_calls": [
                                                {
                                                    "id": "call_search_1",
                                                    "type": "function",
                                                    "function": {
                                                        "name": "web_search",
                                                        "arguments": '{"q":"agent rl"}',
                                                    },
                                                }
                                            ],
                                        }
                                    }
                                ]
                            }
                        ).encode("utf-8")
                    else:
                        response_body = json.dumps(
                            {
                                "choices": [
                                    {
                                        "message": {
                                            "role": "assistant",
                                            "content": (
                                                "ART is SDK-first, while AReaL is proxy-first and "
                                                "better aligned with external runtimes."
                                            ),
                                        }
                                    }
                                ]
                            }
                        ).encode("utf-8")

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response_body)))
                    self.end_headers()
                    self.wfile.write(response_body)

                def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                    return

            class ToolHandler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:  # noqa: N802
                    self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    response_body = json.dumps(
                        {
                            "ok": True,
                            "results": [
                                {
                                    "title": "ART",
                                    "summary": "SDK-first agent RL",
                                },
                                {
                                    "title": "AReaL",
                                    "summary": "proxy-first async agent RL",
                                },
                            ],
                        }
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response_body)))
                    self.end_headers()
                    self.wfile.write(response_body)

                def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                    return

            try:
                model_upstream, model_thread = _start_server(ModelHandler)
                tool_upstream, tool_thread = _start_server(ToolHandler)
                proxy, proxy_thread = _start_server(
                    _build_handler(
                        ProxyConfig(
                            host="127.0.0.1",
                            port=0,
                            store_uri=store_uri,
                            model_upstream=f"http://127.0.0.1:{model_upstream.server_address[1]}/v1/chat/completions",
                            tool_upstream=f"http://127.0.0.1:{tool_upstream.server_address[1]}/tools/run",
                        )
                    )
                )
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")

            try:
                headers = {
                    "x-clawgraph-session-id": "sess_multi_actor",
                    "x-clawgraph-run-id": "run_multi_actor",
                    "x-clawgraph-user-id": "user_multi_actor",
                }

                status_code, _ = _post_json(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    {"messages": [{"role": "user", "content": "compare ART and AReaL"}]},
                    headers={**headers, "x-clawgraph-request-id": "req_model_1"},
                )
                self.assertEqual(status_code, 200)

                status_code, _ = _post_json(
                    f"http://127.0.0.1:{proxy.server_address[1]}/tools/run",
                    {"tool": "web_search", "arguments": {"q": "agent rl"}},
                    headers={**headers, "x-clawgraph-request-id": "req_tool_1"},
                )
                self.assertEqual(status_code, 200)

                status_code, _ = _post_json(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/semantic-events",
                    {
                        "kind": "controller_route_decided",
                        "payload": {
                            "request_id": "req_tool_1",
                            "branch_id": "br_tool_route_1",
                            "branch_type": "subagent",
                            "status": "succeeded",
                        },
                    },
                    headers=headers,
                )
                self.assertEqual(status_code, 202)

                status_code, _ = _post_json(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    {"messages": [{"role": "user", "content": "give the final answer"}]},
                    headers={**headers, "x-clawgraph-request-id": "req_model_2"},
                )
                self.assertEqual(status_code, 200)

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("sess_multi_actor")
                artifacts_plan = plan_artifact_bootstrap(
                    template="request-outcome-scores",
                    facts=facts,
                    producer="integration",
                )
                for artifact in artifacts_plan.artifacts:
                    store.append_artifact(artifact)

                session_summary = build_session_inspect_summary(
                    facts,
                    store.list_artifacts(session_id="sess_multi_actor", latest_only=True),
                )
                self.assertEqual(session_summary.request_count, 3)
                self.assertEqual(session_summary.success_count, 3)

                replay = render_session_replay(
                    facts,
                    store.list_artifacts(session_id="sess_multi_actor", latest_only=True),
                )
                self.assertIn("model /v1/chat/completions", replay)
                self.assertIn("tool /tools/run", replay)

                self.assertEqual(
                    export_dataset(
                        store_uri=store_uri,
                        builder="sft",
                        session="sess_multi_actor",
                        out=out_path,
                    ),
                    2,
                )
                rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(len(rows), 2)
                self.assertIn("tool_calls", rows[0]["messages"][-1])
                self.assertEqual(rows[1]["messages"][-1]["content"].split()[0], "ART")
            finally:
                proxy.shutdown()
                model_upstream.shutdown()
                tool_upstream.shutdown()
                proxy.server_close()
                model_upstream.server_close()
                tool_upstream.server_close()
                proxy_thread.join(timeout=2)
                model_thread.join(timeout=2)
                tool_thread.join(timeout=2)

    def test_retry_semantic_bootstrap_and_export_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream, upstream_thread = _start_server(_make_retry_then_stream_handler())
                proxy, proxy_thread = _start_server(
                    _build_handler(
                        ProxyConfig(
                            host="127.0.0.1",
                            port=0,
                            store_uri=store_uri,
                            model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                        )
                    )
                )
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")

            try:
                session_headers = {
                    "x-clawgraph-session-id": "sess_runtime_1",
                    "x-clawgraph-run-id": "run_runtime_1",
                    "x-clawgraph-user-id": "user_runtime_1",
                }

                status_code, _ = _post_json(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    {"messages": [{"role": "user", "content": "compare repos"}]},
                    headers={**session_headers, "x-clawgraph-request-id": "req_main_1"},
                )
                self.assertEqual(status_code, 502)

                status_code, body = _post_json(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    {
                        "messages": [{"role": "user", "content": "compare repos"}],
                        "stream": True,
                    },
                    headers={**session_headers, "x-clawgraph-request-id": "req_retry_1"},
                )
                self.assertEqual(status_code, 200)
                self.assertIn(b"[DONE]", body)

                status_code, _ = _post_json(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/semantic-events",
                    {
                        "kind": "retry_declared",
                        "payload": {
                            "request_id": "req_retry_1",
                            "parent_request_id": "req_main_1",
                            "branch_id": "br_retry_declared_1",
                            "branch_type": "retry",
                            "status": "succeeded",
                        },
                    },
                    headers=session_headers,
                )
                self.assertEqual(status_code, 202)

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("sess_runtime_1")
                plan = plan_artifact_bootstrap(
                    template="openclaw-defaults",
                    facts=facts,
                    producer="integration",
                )
                self.assertTrue(plan.ready)
                for artifact in plan.artifacts:
                    store.append_artifact(artifact)

                artifacts = store.list_artifacts(session_id="sess_runtime_1", latest_only=True)
                readiness = build_dataset_readiness_summary(
                    facts,
                    artifacts,
                    builder="preference",
                )
                self.assertTrue(readiness.builders[0].ready)

                sft_path = Path(tempdir) / "runtime_sft.jsonl"
                preference_path = Path(tempdir) / "runtime_preference.jsonl"
                self.assertEqual(
                    export_dataset(
                        store_uri=store_uri,
                        builder="sft",
                        session="sess_runtime_1",
                        out=sft_path,
                    ),
                    1,
                )
                self.assertEqual(
                    export_dataset(
                        store_uri=store_uri,
                        builder="preference",
                        session="sess_runtime_1",
                        out=preference_path,
                    ),
                    1,
                )
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_responses_streaming_routing_and_export_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "responses_sft.jsonl"
            store_uri = f"sqlite:///{db_path}"

            responses_handler = _make_responses_stream_handler()
            try:
                upstream, upstream_thread = _start_server(responses_handler)
                proxy, proxy_thread = _start_server(
                    _build_handler(
                        ProxyConfig(
                            host="127.0.0.1",
                            port=0,
                            store_uri=store_uri,
                            model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                        )
                    )
                )
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")

            try:
                status_code, body = _post_json(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/responses",
                    {"input": "search", "stream": True},
                    headers={
                        "x-clawgraph-session-id": "sess_responses_1",
                        "x-clawgraph-run-id": "run_responses_1",
                        "x-clawgraph-request-id": "req_responses_1",
                    },
                )
                self.assertEqual(status_code, 200)
                self.assertIn(b"[DONE]", body)
                self.assertEqual(responses_handler.last_path, "/v1/responses")

                self.assertEqual(
                    export_dataset(
                        store_uri=store_uri,
                        builder="sft",
                        session="sess_responses_1",
                        out=out_path,
                    ),
                    1,
                )
                record = json.loads(out_path.read_text(encoding="utf-8").strip())
                self.assertEqual(record["messages"][-1]["content"], "Need to call search first.")
                self.assertEqual(
                    record["messages"][-1]["tool_calls"][0]["function"]["name"],
                    "web_search",
                )
                self.assertEqual(
                    record["messages"][-1]["tool_calls"][0]["function"]["arguments"],
                    '{"q":"agent rl"}',
                )
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
