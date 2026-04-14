from __future__ import annotations

import gzip
import json
import tempfile
import threading
import unittest
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from clawgraph.proxy.payload_store import LocalPayloadStore
from clawgraph.proxy.server import (
    ProxyConfig,
    _actor_for_path,
    _build_handler,
    _canonical_response_payload,
    _build_stream_response_json,
    _cookie_value,
    _extract_complete_sse_fragments,
    _extract_sse_fragments,
    _is_streaming_content_type,
    _is_streaming_request,
    _payload_from_response,
    _resolve_upstream_url,
    _update_stream_state,
    _target_upstream,
)
from clawgraph.export import export_dataset
from clawgraph.store import SQLiteFactStore


class _UpstreamHandler(BaseHTTPRequestHandler):
    last_cookie: str | None = None
    last_new_run_header: str | None = None
    last_method: str | None = None
    last_path: str | None = None
    last_task_id: str | None = None
    last_authorization: str | None = None
    last_proxy_auth_header: str | None = None

    def _write_json(self, payload: dict[str, object]) -> None:
        response_body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def do_GET(self) -> None:  # noqa: N802
        type(self).last_method = "GET"
        type(self).last_path = self.path
        type(self).last_cookie = self.headers.get("Cookie")
        type(self).last_new_run_header = self.headers.get("x-clawgraph-new-run")
        type(self).last_task_id = self.headers.get("x-clawgraph-task-id")
        type(self).last_authorization = self.headers.get("Authorization")
        type(self).last_proxy_auth_header = self.headers.get("x-clawgraph-proxy-auth")
        self._write_json({"object": "list", "path": self.path})

    def do_POST(self) -> None:  # noqa: N802
        type(self).last_method = "POST"
        type(self).last_path = self.path
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).last_cookie = self.headers.get("Cookie")
        type(self).last_new_run_header = self.headers.get("x-clawgraph-new-run")
        type(self).last_task_id = self.headers.get("x-clawgraph-task-id")
        type(self).last_authorization = self.headers.get("Authorization")
        type(self).last_proxy_auth_header = self.headers.get("x-clawgraph-proxy-auth")
        request_json = json.loads(body.decode("utf-8"))
        self._write_json(
            {
                "id": "cmpl_1",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": f"echo:{request_json['messages'][-1]['content']}",
                        }
                    }
                ],
            }
        )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class _StreamingUpstreamHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        request_json = json.loads(body.decode("utf-8"))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for token in ("echo:", request_json["messages"][-1]["content"]):
            chunk = (
                'data: {"choices":[{"delta":{"role":"assistant","content":"'
                + token
                + '"}}]}\n\n'
            ).encode("utf-8")
            self.wfile.write(chunk)
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class _LargeResponseUpstreamHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        response_body = json.dumps({"payload": "x" * 2048}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class ProxyCaptureTest(unittest.TestCase):
    def test_helper_functions(self) -> None:
        url = _resolve_upstream_url("https://example.com", "/v1/chat/completions")
        self.assertEqual(url, "https://example.com/v1/chat/completions")
        root_chat_url = _resolve_upstream_url(
            "https://example.com/v1/chat/completions",
            "/chat/completions",
        )
        self.assertEqual(root_chat_url, "https://example.com/v1/chat/completions")
        responses_url = _resolve_upstream_url(
            "https://example.com/v1/chat/completions",
            "/v1/responses",
        )
        self.assertEqual(responses_url, "https://example.com/v1/responses")
        root_responses_url = _resolve_upstream_url(
            "https://example.com/v1/chat/completions",
            "/responses",
        )
        self.assertEqual(root_responses_url, "https://example.com/v1/responses")
        prefixed_responses_url = _resolve_upstream_url(
            "https://example.com/openai/v1/chat/completions",
            "/v1/responses",
        )
        self.assertEqual(prefixed_responses_url, "https://example.com/openai/v1/responses")
        config = ProxyConfig(
            host="127.0.0.1",
            port=8080,
            store_uri="sqlite:///ignored.db",
            model_upstream="https://model.example",
            tool_upstream="https://tool.example",
        )
        self.assertEqual(_target_upstream("/v1/chat/completions", config), "https://model.example")
        self.assertEqual(_target_upstream("/v1/responses", config), "https://model.example")
        self.assertEqual(_target_upstream("/chat/completions", config), "https://model.example")
        self.assertEqual(_target_upstream("/responses", config), "https://model.example")
        self.assertEqual(_target_upstream("/v1/semantic-events", config), None)
        self.assertEqual(_actor_for_path("/v1/chat/completions"), "model")
        self.assertEqual(_actor_for_path("/v1/responses"), "model")
        self.assertEqual(_actor_for_path("/chat/completions"), "model")
        self.assertEqual(_actor_for_path("/responses"), "model")
        self.assertEqual(_actor_for_path("/tools/run"), "tool")
        self.assertEqual(
            _cookie_value({"Cookie": "clawgraph_session_id=sess_cookie"}, "clawgraph_session_id"),
            "sess_cookie",
        )

        payload = _payload_from_response(
            path="/v1/chat/completions",
            status_code=200,
            content_type="application/json",
            response_body=json.dumps({"ok": True}).encode("utf-8"),
            max_capture_bytes=1024,
        )
        self.assertEqual(payload["status_code"], 200)
        self.assertEqual(payload["json"]["ok"], True)
        self.assertTrue(_is_streaming_request({"stream": True}))
        self.assertTrue(_is_streaming_content_type("text/event-stream"))

        canonical_chat = _canonical_response_payload(
            path="/chat/completions",
            response_json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup",
                                        "arguments": '{"q":"agent rl"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )
        self.assertEqual(
            canonical_chat["assistant_message"]["tool_calls"][0]["function"]["name"],
            "lookup",
        )

        fragments = _extract_sse_fragments(
            b'data: {"choices":[{"delta":{"content":"hel"}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        self.assertEqual(fragments[0]["type"], "json")
        self.assertEqual(fragments[-1]["type"], "done")

        stream_state = {"role": "assistant", "delta_parts": [], "fallback_text": None}
        _update_stream_state(stream_state, fragments)
        stream_json = _build_stream_response_json("/chat/completions", stream_state)
        self.assertEqual(
            stream_json,
            {"choices": [{"message": {"role": "assistant", "content": "hello"}}]},
        )

        pending = bytearray()
        first = _extract_complete_sse_fragments(
            pending=pending,
            chunk=b'data: {"choices":[{"delta":{"content":"he',
        )
        self.assertEqual(first, [])
        second = _extract_complete_sse_fragments(
            pending=pending,
            chunk=b'llo"}}]}\r\n\r\n',
        )
        self.assertEqual(second[0]["type"], "json")

        tool_state = {
            "role": "assistant",
            "delta_parts": [],
            "fallback_text": None,
            "tool_calls": {},
            "response_output_items": {},
            "response_output_order": [],
            "output_text_parts": [],
        }
        _update_stream_state(
            tool_state,
            [
                {
                    "type": "json",
                    "data": {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {"name": "lookup", "arguments": '{"q":"he'},
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                },
                {
                    "type": "json",
                    "data": {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "function": {"arguments": 'llo"}'},
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                },
            ],
        )
        tool_stream_json = _build_stream_response_json("/chat/completions", tool_state)
        self.assertEqual(
            tool_stream_json["choices"][0]["message"]["tool_calls"][0]["function"]["name"],
            "lookup",
        )
        self.assertEqual(
            tool_stream_json["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"],
            '{"q":"hello"}',
        )

        responses_state = {
            "role": "assistant",
            "delta_parts": [],
            "fallback_text": None,
            "tool_calls": {},
            "response_output_items": {},
            "response_output_order": [],
            "output_text_parts": [],
        }
        _update_stream_state(
            responses_state,
            [
                {
                    "type": "json",
                    "data": {
                        "type": "response.output_item.added",
                        "output_index": 0,
                        "item": {
                            "id": "msg_1",
                            "type": "message",
                            "role": "assistant",
                        },
                    },
                },
                {
                    "type": "json",
                    "data": {
                        "type": "response.output_text.delta",
                        "item_id": "msg_1",
                        "delta": "hello",
                    },
                },
                {
                    "type": "json",
                    "data": {
                        "type": "response.output_item.added",
                        "output_index": 1,
                        "item": {
                            "id": "fc_1",
                            "type": "function_call",
                            "name": "lookup",
                            "call_id": "call_1",
                        },
                    },
                },
                {
                    "type": "json",
                    "data": {
                        "type": "response.function_call_arguments.delta",
                        "item_id": "fc_1",
                        "delta": '{"q":"world"}',
                    },
                },
            ],
        )
        responses_json = _build_stream_response_json("/responses", responses_state)
        self.assertEqual(responses_json["output_text"], "hello")
        self.assertEqual(responses_json["output"][0]["content"][0]["text"], "hello")
        self.assertEqual(responses_json["output"][1]["name"], "lookup")
        self.assertEqual(responses_json["output"][1]["arguments"], '{"q":"world"}')

        canonical_responses = _canonical_response_payload(
            path="/responses",
            response_json=responses_json,
        )
        self.assertEqual(
            canonical_responses["assistant_message"]["tool_calls"][0]["function"]["name"],
            "lookup",
        )

    def test_proxy_captures_and_forwards(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            upstream_url = (
                f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions"
            )
            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=upstream_url,
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps(
                    {
                        "messages": [{"role": "user", "content": "hello"}],
                    }
                ).encode("utf-8")
                request = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer upstream-secret",
                        "Cookie": (
                            "clawgraph_session_id=session_test; "
                            "clawgraph_run_id=run_test; auth_token=secret; sticky=1"
                        ),
                        "x-clawgraph-session-id": "session_test",
                        "x-clawgraph-request-id": "req_test",
                        "x-clawgraph-user-id": "user_test",
                    },
                    method="POST",
                )
                with urlopen(request) as response:
                    body = json.loads(response.read().decode("utf-8"))
                    echoed_request_id = response.headers.get("x-clawgraph-request-id")

                self.assertEqual(body["choices"][0]["message"]["content"], "echo:hello")
                self.assertEqual(echoed_request_id, "req_test")
                self.assertEqual(_UpstreamHandler.last_cookie, "auth_token=secret; sticky=1")
                self.assertEqual(_UpstreamHandler.last_method, "POST")
                self.assertEqual(_UpstreamHandler.last_authorization, "Bearer upstream-secret")
                self.assertIsNone(_UpstreamHandler.last_proxy_auth_header)

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("session_test")
                self.assertEqual(len(facts), 2)
                self.assertEqual(facts[0].kind, "request_started")
                self.assertEqual(facts[1].kind, "response_finished")
                self.assertEqual(facts[0].request_id, "req_test")
                self.assertEqual(facts[0].user_id, "user_test")
                self.assertEqual(facts[1].request_id, "req_test")
                self.assertEqual(facts[0].payload["headers"]["Authorization"], "***")
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_proxy_captures_openai_sdk_root_chat_path(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            upstream_url = (
                f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions"
            )
            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=upstream_url,
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps(
                    {
                        "messages": [{"role": "user", "content": "sdk-root"}],
                    }
                ).encode("utf-8")
                request = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/chat/completions",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request) as response:
                    body = json.loads(response.read().decode("utf-8"))

                self.assertEqual(body["choices"][0]["message"]["content"], "echo:sdk-root")
                self.assertEqual(_UpstreamHandler.last_path, "/v1/chat/completions")

                store = SQLiteFactStore(store_uri)
                session_id = store.get_latest_session_id()
                self.assertIsNotNone(session_id)
                facts = store.list_facts(session_id=session_id)
                self.assertEqual(len(facts), 2)
                self.assertEqual(facts[0].payload["path"], "/chat/completions")
                self.assertEqual(facts[1].payload["path"], "/chat/completions")
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_proxy_forwards_get_and_captures_original_method(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            upstream_url = (
                f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions"
            )
            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=upstream_url,
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                with urlopen(
                    Request(
                        (
                            f"http://127.0.0.1:{proxy.server_address[1]}"
                            "/v1/models?limit=1"
                        ),
                        headers={
                            "x-clawgraph-session-id": "session_get",
                            "x-clawgraph-request-id": "req_get",
                        },
                        method="GET",
                    )
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))

                self.assertEqual(payload["path"], "/v1/models?limit=1")
                self.assertEqual(_UpstreamHandler.last_method, "GET")
                self.assertEqual(_UpstreamHandler.last_path, "/v1/models?limit=1")

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("session_get")
                self.assertEqual(facts[0].payload["method"], "GET")
                self.assertEqual(facts[0].payload["path"], "/v1/models")
                self.assertEqual(facts[0].payload["request_target"], "/v1/models?limit=1")
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_proxy_keeps_task_id_separate_from_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps(
                    {
                        "task_id": "task_123",
                        "messages": [{"role": "user", "content": "hello"}],
                    }
                ).encode("utf-8")
                with urlopen(
                    Request(
                        f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                        data=payload,
                        headers={
                            "Content-Type": "application/json",
                            "x-clawgraph-session-id": "session_task",
                        },
                        method="POST",
                    )
                ) as response:
                    run_id = response.headers.get("x-clawgraph-run-id")
                    response.read()

                self.assertIsNotNone(run_id)
                self.assertNotEqual(run_id, "task_123")
                self.assertEqual(_UpstreamHandler.last_task_id, "task_123")

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("session_task")
                self.assertEqual(facts[0].task_id, "task_123")
                self.assertNotEqual(facts[0].run_id, "task_123")
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_proxy_spills_large_request_and_response_payloads_to_local_files(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            payload_dir = Path(tempdir) / "payloads"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _LargeResponseUpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                        max_capture_bytes=64,
                        max_response_body_bytes=4096,
                        payload_dir=str(payload_dir),
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps(
                    {
                        "messages": [
                            {
                                "role": "user",
                                "content": "payload-sidecar-" * 12,
                            }
                        ]
                    }
                ).encode("utf-8")
                request = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "x-clawgraph-session-id": "session_spill",
                        "x-clawgraph-request-id": "req_spill",
                    },
                    method="POST",
                )
                with urlopen(request) as response:
                    response_body = response.read()

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("session_spill")
                request_payload = facts[0].payload
                response_payload = facts[1].payload
                self.assertTrue(request_payload["capture_truncated"])
                self.assertTrue(response_payload["capture_truncated"])
                self.assertNotIn("json", request_payload)
                self.assertNotIn("json", response_payload)

                request_ref = request_payload["body_ref"]
                response_ref = response_payload["body_ref"]
                payload_store = LocalPayloadStore(root_dir=payload_dir, store_uri=store_uri)
                with gzip.open(payload_store.resolve_body_path(request_ref), "rb") as handle:
                    self.assertEqual(handle.read(), payload)
                with gzip.open(payload_store.resolve_body_path(response_ref), "rb") as handle:
                    self.assertEqual(handle.read(), response_body)
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_proxy_streaming_capture_supports_sft_export(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "sft.jsonl"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingUpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps(
                    {
                        "messages": [{"role": "user", "content": "hello"}],
                        "stream": True,
                    }
                ).encode("utf-8")
                request = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "x-clawgraph-session-id": "session_stream",
                        "x-clawgraph-request-id": "req_stream",
                    },
                    method="POST",
                )
                with urlopen(request) as response:
                    body = response.read().decode("utf-8")

                self.assertIn("data: [DONE]", body)

                count = export_dataset(
                    store_uri=store_uri,
                    builder="sft",
                    session="session_stream",
                    out=out_path,
                )
                self.assertEqual(count, 1)
                record = json.loads(out_path.read_text(encoding="utf-8").strip())
                self.assertEqual(record["messages"][-1]["content"], "echo:hello")
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_proxy_streaming_payload_spills_to_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            payload_dir = Path(tempdir) / "payloads"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingUpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                        max_capture_bytes=8,
                        payload_dir=str(payload_dir),
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps(
                    {
                        "messages": [{"role": "user", "content": "hello"}],
                        "stream": True,
                    }
                ).encode("utf-8")
                request = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "x-clawgraph-session-id": "session_stream_spill",
                        "x-clawgraph-request-id": "req_stream_spill",
                    },
                    method="POST",
                )
                with urlopen(request) as response:
                    streamed_body = response.read()

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("session_stream_spill")
                response_payload = [fact for fact in facts if fact.kind == "response_finished"][0].payload
                self.assertTrue(response_payload["capture_truncated"])
                payload_store = LocalPayloadStore(root_dir=payload_dir, store_uri=store_uri)
                with gzip.open(
                    payload_store.resolve_body_path(response_payload["body_ref"]),
                    "rb",
                ) as handle:
                    self.assertEqual(handle.read(), streamed_body)
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_proxy_auto_assigns_session_cookie_without_manual_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps(
                    {
                        "messages": [{"role": "user", "content": "hello"}],
                    }
                ).encode("utf-8")
                url = f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions"

                first_request = Request(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(first_request) as response:
                    first_session_id = response.headers.get("x-clawgraph-session-id")
                    first_run_id = response.headers.get("x-clawgraph-run-id")
                    first_request_id = response.headers.get("x-clawgraph-request-id")
                    set_cookies = response.headers.get_all("Set-Cookie")
                    response.read()

                self.assertIsNotNone(first_session_id)
                self.assertTrue(first_run_id.startswith("run_"))
                self.assertTrue(first_request_id.startswith("req_"))
                self.assertEqual(len(set_cookies), 2)
                cookie = SimpleCookie()
                for set_cookie in set_cookies:
                    cookie.load(set_cookie)
                cookie_header = "; ".join(
                    f"{morsel.key}={morsel.value}" for morsel in cookie.values()
                )
                self.assertIn("clawgraph_session_id=", cookie_header)
                self.assertIn("clawgraph_run_id=", cookie_header)

                second_request = Request(
                    url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Cookie": cookie_header,
                    },
                    method="POST",
                )
                with urlopen(second_request) as response:
                    second_session_id = response.headers.get("x-clawgraph-session-id")
                    second_run_id = response.headers.get("x-clawgraph-run-id")
                    second_request_id = response.headers.get("x-clawgraph-request-id")
                    response.read()

                self.assertEqual(second_session_id, first_session_id)
                self.assertEqual(second_run_id, first_run_id)
                self.assertNotEqual(second_request_id, first_request_id)
                self.assertIsNone(_UpstreamHandler.last_cookie)
                self.assertIsNone(_UpstreamHandler.last_new_run_header)

                third_request = Request(
                    url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Cookie": cookie_header,
                        "x-clawgraph-new-run": "1",
                    },
                    method="POST",
                )
                with urlopen(third_request) as response:
                    third_session_id = response.headers.get("x-clawgraph-session-id")
                    third_run_id = response.headers.get("x-clawgraph-run-id")
                    response.read()

                self.assertEqual(third_session_id, first_session_id)
                self.assertNotEqual(third_run_id, second_run_id)
                self.assertIsNone(_UpstreamHandler.last_new_run_header)

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts(first_session_id)
                request_ids = [fact.request_id for fact in facts if fact.kind == "request_started"]
                self.assertEqual(len(request_ids), 3)
                self.assertEqual(facts[0].run_id, first_run_id)
                self.assertEqual(facts[2].run_id, second_run_id)
                self.assertEqual(facts[4].run_id, third_run_id)
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_proxy_requires_auth_token_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                        auth_token="secret-token",
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps({"messages": [{"role": "user", "content": "hello"}]}).encode(
                    "utf-8"
                )
                unauthorized = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer secret-token",
                    },
                    method="POST",
                )
                with self.assertRaises(HTTPError) as cm:
                    urlopen(unauthorized)
                self.assertEqual(cm.exception.code, 401)

                authorized = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer upstream-secret",
                        "x-clawgraph-proxy-auth": "secret-token",
                        "x-clawgraph-session-id": "session_auth",
                    },
                    method="POST",
                )
                with urlopen(authorized) as response:
                    body = json.loads(response.read().decode("utf-8"))
                self.assertEqual(body["choices"][0]["message"]["content"], "echo:hello")
                self.assertEqual(_UpstreamHandler.last_authorization, "Bearer upstream-secret")
                self.assertIsNone(_UpstreamHandler.last_proxy_auth_header)

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("session_auth")
                sanitized_headers = {
                    key.lower(): value for key, value in facts[0].payload["headers"].items()
                }
                self.assertEqual(sanitized_headers["authorization"], "***")
                self.assertEqual(sanitized_headers["x-clawgraph-proxy-auth"], "***")
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_proxy_can_inject_upstream_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                        upstream_api_key="upstream-secret",
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps({"messages": [{"role": "user", "content": "hello"}]}).encode(
                    "utf-8"
                )
                request = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer client-placeholder",
                        "x-clawgraph-session-id": "session_upstream_auth",
                    },
                    method="POST",
                )
                with urlopen(request) as response:
                    body = json.loads(response.read().decode("utf-8"))

                self.assertEqual(body["choices"][0]["message"]["content"], "echo:hello")
                self.assertEqual(_UpstreamHandler.last_authorization, "Bearer upstream-secret")

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("session_upstream_auth")
                sanitized_headers = {
                    key.lower(): value for key, value in facts[0].payload["headers"].items()
                }
                self.assertEqual(sanitized_headers["authorization"], "***")
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_proxy_rejects_session_owner_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps({"messages": [{"role": "user", "content": "hello"}]}).encode(
                    "utf-8"
                )
                first = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "x-clawgraph-session-id": "session_owner",
                        "x-clawgraph-user-id": "user_a",
                    },
                    method="POST",
                )
                with urlopen(first) as response:
                    response.read()

                second = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "x-clawgraph-session-id": "session_owner",
                        "x-clawgraph-user-id": "user_b",
                    },
                    method="POST",
                )
                with self.assertRaises(HTTPError) as cm:
                    urlopen(second)
                self.assertEqual(cm.exception.code, 409)
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_proxy_rejects_oversized_request_body(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                        max_request_body_bytes=32,
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps(
                    {"messages": [{"role": "user", "content": "this request body is too large"}]}
                ).encode("utf-8")
                request = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as cm:
                    urlopen(request)
                self.assertEqual(cm.exception.code, 413)
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_proxy_rejects_oversized_upstream_response(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream = ThreadingHTTPServer(("127.0.0.1", 0), _LargeResponseUpstreamHandler)
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                        model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                        max_response_body_bytes=256,
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps({"messages": [{"role": "user", "content": "hello"}]}).encode(
                    "utf-8"
                )
                request = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as cm:
                    urlopen(request)
                self.assertEqual(cm.exception.code, 502)

                store = SQLiteFactStore(store_uri)
                session_id = store.get_latest_session_id()
                self.assertIsNotNone(session_id)
                facts = store.list_facts(session_id)
                self.assertEqual(facts[-1].kind, "error_raised")
                self.assertEqual(facts[-1].payload["error_code"], "upstream_response_too_large")
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_semantic_event_rejects_unknown_request_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"
            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _build_handler(
                    ProxyConfig(
                        host="127.0.0.1",
                        port=0,
                        store_uri=store_uri,
                    )
                ),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                payload = json.dumps(
                    {
                        "kind": "retry_declared",
                        "payload": {"request_id": "missing_request"},
                    }
                ).encode("utf-8")
                request = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/semantic-events",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "x-clawgraph-session-id": "session_semantic",
                        "x-clawgraph-run-id": "run_semantic",
                    },
                    method="POST",
                )
                with self.assertRaises(HTTPError) as cm:
                    urlopen(request)
                self.assertEqual(cm.exception.code, 400)
            finally:
                proxy.shutdown()
                proxy.server_close()
                proxy_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
