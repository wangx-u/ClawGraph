from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from clawgraph.proxy import ProxyConfig
from clawgraph.proxy.server import _build_handler
from clawgraph.store import SQLiteFactStore


def _start_server(handler_cls: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


class FailureIntegrationTest(unittest.TestCase):
    def test_upstream_timeout_records_gateway_timeout(self) -> None:
        class SlowHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                time.sleep(0.3)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream, upstream_thread = _start_server(SlowHandler)
                proxy, proxy_thread = _start_server(
                    _build_handler(
                        ProxyConfig(
                            host="127.0.0.1",
                            port=0,
                            store_uri=store_uri,
                            model_upstream=f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions",
                            upstream_timeout_seconds=0.05,
                        )
                    )
                )
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")

            try:
                request = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=json.dumps({"messages": [{"role": "user", "content": "hi"}]}).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "x-clawgraph-session-id": "sess_timeout",
                        "x-clawgraph-request-id": "req_timeout",
                    },
                    method="POST",
                )
                with self.assertRaises(HTTPError) as cm:
                    urlopen(request)
                self.assertEqual(cm.exception.code, 504)

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("sess_timeout")
                self.assertEqual(facts[-1].kind, "error_raised")
                self.assertEqual(facts[-1].payload["error_code"], "upstream_timeout")
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_truncated_stream_marks_stream_incomplete(self) -> None:
        class TruncatedStreamHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(
                    b'data: {"choices":[{"delta":{"role":"assistant","content":"partial"}}]}\n\n'
                )
                self.wfile.flush()

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream, upstream_thread = _start_server(TruncatedStreamHandler)
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
                request = Request(
                    f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
                    data=json.dumps(
                        {"messages": [{"role": "user", "content": "hi"}], "stream": True}
                    ).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "x-clawgraph-session-id": "sess_truncated",
                        "x-clawgraph-request-id": "req_truncated",
                    },
                    method="POST",
                )
                with urlopen(request) as response:
                    body = response.read().decode("utf-8")
                self.assertIn("partial", body)

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("sess_truncated")
                response_fact = next(fact for fact in facts if fact.kind == "response_finished")
                self.assertFalse(response_fact.payload["stream_complete"])
                self.assertEqual(
                    response_fact.payload["canonical"]["assistant_message"]["content"],
                    "partial",
                )
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)

    def test_client_disconnect_marks_stream_payload(self) -> None:
        class LongStreamHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for token in ("one", "two", "three", "four"):
                    self.wfile.write(
                        f'data: {json.dumps({"choices":[{"delta":{"role":"assistant","content":token}}]})}\n\n'.encode(
                            "utf-8"
                        )
                    )
                    self.wfile.flush()
                    time.sleep(0.05)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream, upstream_thread = _start_server(LongStreamHandler)
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
                sock = socket.create_connection(("127.0.0.1", proxy.server_address[1]))
                request_body = json.dumps(
                    {"messages": [{"role": "user", "content": "disconnect"}], "stream": True}
                ).encode("utf-8")
                raw_request = (
                    b"POST /v1/chat/completions HTTP/1.1\r\n"
                    + b"Host: 127.0.0.1\r\n"
                    + b"Content-Type: application/json\r\n"
                    + b"x-clawgraph-session-id: sess_disconnect\r\n"
                    + b"x-clawgraph-request-id: req_disconnect\r\n"
                    + f"Content-Length: {len(request_body)}\r\n\r\n".encode("utf-8")
                    + request_body
                )
                sock.sendall(raw_request)
                sock.recv(256)
                sock.close()
                time.sleep(0.25)

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts("sess_disconnect")
                response_fact = next(fact for fact in facts if fact.kind == "response_finished")
                self.assertTrue(response_fact.payload["client_disconnected"])
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
