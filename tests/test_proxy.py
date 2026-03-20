from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

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

    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).last_cookie = self.headers.get("Cookie")
        request_json = json.loads(body.decode("utf-8"))
        response_body = json.dumps(
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
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

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


class ProxyCaptureTest(unittest.TestCase):
    def test_helper_functions(self) -> None:
        url = _resolve_upstream_url("https://example.com", "/v1/chat/completions")
        self.assertEqual(url, "https://example.com/v1/chat/completions")
        responses_url = _resolve_upstream_url(
            "https://example.com/v1/chat/completions",
            "/v1/responses",
        )
        self.assertEqual(responses_url, "https://example.com/v1/responses")
        config = ProxyConfig(
            host="127.0.0.1",
            port=8080,
            store_uri="sqlite:///ignored.db",
            model_upstream="https://model.example",
            tool_upstream="https://tool.example",
        )
        self.assertEqual(_target_upstream("/v1/chat/completions", config), "https://model.example")
        self.assertEqual(_target_upstream("/v1/responses", config), "https://model.example")
        self.assertEqual(_target_upstream("/v1/semantic-events", config), None)
        self.assertEqual(_actor_for_path("/v1/chat/completions"), "model")
        self.assertEqual(_actor_for_path("/v1/responses"), "model")
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
        )
        self.assertEqual(payload["status_code"], 200)
        self.assertEqual(payload["json"]["ok"], True)
        self.assertTrue(_is_streaming_request({"stream": True}))
        self.assertTrue(_is_streaming_content_type("text/event-stream"))

        canonical_chat = _canonical_response_payload(
            path="/v1/chat/completions",
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
        stream_json = _build_stream_response_json("/v1/chat/completions", stream_state)
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
        tool_stream_json = _build_stream_response_json("/v1/chat/completions", tool_state)
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
        responses_json = _build_stream_response_json("/v1/responses", responses_state)
        self.assertEqual(responses_json["output_text"], "hello")
        self.assertEqual(responses_json["output"][0]["content"][0]["text"], "hello")
        self.assertEqual(responses_json["output"][1]["name"], "lookup")
        self.assertEqual(responses_json["output"][1]["arguments"], '{"q":"world"}')

        canonical_responses = _canonical_response_payload(
            path="/v1/responses",
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
                self.assertIsNone(_UpstreamHandler.last_cookie)

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("session_test")
                self.assertEqual(len(facts), 2)
                self.assertEqual(facts[0].kind, "request_started")
                self.assertEqual(facts[1].kind, "response_finished")
                self.assertEqual(facts[0].request_id, "req_test")
                self.assertEqual(facts[0].user_id, "user_test")
                self.assertEqual(facts[1].request_id, "req_test")
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
                    cookie_header = response.headers.get("Set-Cookie")
                    response.read()

                self.assertIsNotNone(first_session_id)
                self.assertEqual(first_run_id, first_session_id)
                self.assertTrue(first_request_id.startswith("req_"))
                self.assertIn("clawgraph_session_id=", cookie_header)

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
                self.assertEqual(second_run_id, first_session_id)
                self.assertNotEqual(second_request_id, first_request_id)
                self.assertIsNone(_UpstreamHandler.last_cookie)

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts(first_session_id)
                request_ids = [fact.request_id for fact in facts if fact.kind == "request_started"]
                self.assertEqual(len(request_ids), 2)
                self.assertEqual(facts[0].run_id, first_session_id)
                self.assertEqual(facts[2].run_id, first_session_id)
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
