from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from clawgraph import ClawGraphRuntimeClient
from clawgraph.runtime.client import ClawGraphSession
from clawgraph.proxy import ProxyConfig
from clawgraph.proxy.server import _build_handler
from clawgraph.store import SQLiteFactStore


class _ModelHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.loads(body.decode("utf-8"))
        content = payload.get("messages", [{"content": ""}])[-1]["content"]
        response_body = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": f"echo:{content}",
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


def _start_server(handler_cls: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


class RuntimeClientIntegrationTest(unittest.TestCase):
    def test_session_absorbs_explicit_clawgraph_headers(self) -> None:
        session = ClawGraphSession()

        headers = session.request_headers(
            extra_headers={
                "x-clawgraph-session-id": "sess_explicit",
                "x-clawgraph-run-id": "run_explicit",
                "x-clawgraph-user-id": "user_explicit",
            }
        )

        self.assertEqual(headers["x-clawgraph-session-id"], "sess_explicit")
        self.assertEqual(headers["x-clawgraph-run-id"], "run_explicit")
        self.assertEqual(session.session_id, "sess_explicit")
        self.assertEqual(session.run_id, "run_explicit")
        self.assertEqual(session.user_id, "user_explicit")

    def test_session_can_start_new_run_without_rotating_session(self) -> None:
        session = ClawGraphSession()

        first_headers = session.request_headers()
        first_session_id = first_headers["x-clawgraph-session-id"]
        first_run_id = first_headers["x-clawgraph-run-id"]

        second_run_id = session.start_new_run()
        second_headers = session.request_headers()

        self.assertEqual(second_headers["x-clawgraph-session-id"], first_session_id)
        self.assertEqual(second_headers["x-clawgraph-run-id"], second_run_id)
        self.assertNotEqual(second_run_id, first_run_id)

    def test_runtime_client_reuses_proxy_assigned_session_and_emits_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            try:
                upstream, upstream_thread = _start_server(_ModelHandler)
                proxy, proxy_thread = _start_server(
                    _build_handler(
                        ProxyConfig(
                            host="127.0.0.1",
                            port=0,
                            store_uri=store_uri,
                            model_upstream=(
                                f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions"
                            ),
                        )
                    )
                )
            except PermissionError as exc:
                self.skipTest(f"socket bind not permitted in sandbox: {exc}")

            try:
                client = ClawGraphRuntimeClient(
                    base_url=f"http://127.0.0.1:{proxy.server_address[1]}",
                )
                first = client.chat_completions(
                    {"messages": [{"role": "user", "content": "hello"}]}
                )
                second = client.chat_completions(
                    {"messages": [{"role": "user", "content": "world"}]}
                )

                self.assertEqual(first.status_code, 200)
                self.assertEqual(second.status_code, 200)
                self.assertIsNotNone(client.session.session_id)
                self.assertIsNotNone(client.session.run_id)
                self.assertNotEqual(client.session.session_id, client.session.run_id)
                self.assertEqual(
                    first.headers.get("x-clawgraph-run-id"),
                    second.headers.get("x-clawgraph-run-id"),
                )

                semantic = client.emit_semantic(
                    kind="retry_declared",
                    payload={
                        "branch_type": "retry",
                        "status": "succeeded",
                    },
                    branch_id="br_retry_runtime_client_1",
                )
                self.assertEqual(semantic.status_code, 202)

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts(client.session.session_id)
                request_started = [fact for fact in facts if fact.kind == "request_started"]
                response_finished = [fact for fact in facts if fact.kind == "response_finished"]
                semantic_facts = [fact for fact in facts if fact.kind == "semantic_event"]

                self.assertEqual(len(request_started), 2)
                self.assertEqual(len(response_finished), 2)
                self.assertEqual(len(semantic_facts), 1)
                self.assertTrue(all(fact.run_id == client.session.run_id for fact in facts))
                self.assertEqual(
                    semantic_facts[0].payload["payload"]["request_id"],
                    second.headers["x-clawgraph-request-id"],
                )
                self.assertEqual(
                    semantic_facts[0].payload["payload"]["branch_id"],
                    "br_retry_runtime_client_1",
                )
                self.assertNotEqual(
                    semantic_facts[0].request_id,
                    second.headers["x-clawgraph-request-id"],
                )
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)
