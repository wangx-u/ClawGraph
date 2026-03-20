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
    _extract_sse_fragments,
    _is_streaming_content_type,
    _is_streaming_request,
    _payload_from_response,
    _resolve_upstream_url,
    _target_upstream,
)
from clawgraph.store import SQLiteFactStore


class _UpstreamHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
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


class ProxyCaptureTest(unittest.TestCase):
    def test_helper_functions(self) -> None:
        url = _resolve_upstream_url("https://example.com", "/v1/chat/completions")
        self.assertEqual(url, "https://example.com/v1/chat/completions")
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

        fragments = _extract_sse_fragments(
            b'data: {"choices":[{"delta":{"content":"hel"}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        self.assertEqual(fragments[0]["type"], "json")
        self.assertEqual(fragments[-1]["type"], "done")

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


if __name__ == "__main__":
    unittest.main()
