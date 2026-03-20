from __future__ import annotations

import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from clawgraph import ClawGraphOpenAIClient
from clawgraph.proxy import ProxyConfig
from clawgraph.proxy.server import _build_handler
from clawgraph.store import SQLiteFactStore


class _FakeCreateEndpoint:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def create(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.calls.append((args, kwargs))
        return {"ok": True, "extra_headers": kwargs.get("extra_headers")}


class _FakeChatNamespace:
    def __init__(self) -> None:
        self.completions = _FakeCreateEndpoint()


class _FakeResponsesNamespace:
    def __init__(self) -> None:
        self.create_endpoint = _FakeCreateEndpoint()

    def create(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self.create_endpoint.create(*args, **kwargs)


class _FakeOpenAIClient:
    def __init__(self, *, base_url: str | None = None) -> None:
        self.base_url = base_url
        self.chat = _FakeChatNamespace()
        self.responses = _FakeResponsesNamespace()


class _FakeChatOnlyClient:
    def __init__(self, *, base_url: str | None = None) -> None:
        self.base_url = base_url
        self.chat = _FakeChatNamespace()


class RuntimeOpenAIWrapperTest(unittest.TestCase):
    def test_wrapper_injects_headers_for_chat_and_responses(self) -> None:
        client = _FakeOpenAIClient(base_url="http://127.0.0.1:8080")
        wrapped = ClawGraphOpenAIClient(client)

        chat_result = wrapped.chat.completions.create(
            model="gpt-test",
            messages=[{"role": "user", "content": "hello"}],
        )
        responses_result = wrapped.responses.create(
            model="gpt-test",
            input="hello",
        )

        chat_headers = chat_result["extra_headers"]
        responses_headers = responses_result["extra_headers"]

        self.assertEqual(chat_headers["x-clawgraph-session-id"], responses_headers["x-clawgraph-session-id"])
        self.assertEqual(chat_headers["x-clawgraph-run-id"], responses_headers["x-clawgraph-run-id"])
        self.assertNotEqual(chat_headers["x-clawgraph-request-id"], responses_headers["x-clawgraph-request-id"])
        self.assertTrue(chat_headers["x-clawgraph-session-id"].startswith("sess_"))

    def test_wrapper_merges_existing_extra_headers(self) -> None:
        client = _FakeOpenAIClient(base_url="http://127.0.0.1:8080")
        wrapped = ClawGraphOpenAIClient(client)

        result = wrapped.chat.completions.create(
            model="gpt-test",
            messages=[{"role": "user", "content": "hello"}],
            extra_headers={"x-trace-id": "trace_1"},
            parent_id="fact_parent_1",
        )

        headers = result["extra_headers"]
        self.assertEqual(headers["x-trace-id"], "trace_1")
        self.assertEqual(headers["x-clawgraph-parent-id"], "fact_parent_1")

    def test_wrapper_degrades_to_chat_only_when_responses_is_missing(self) -> None:
        client = _FakeChatOnlyClient(base_url="http://127.0.0.1:8080")
        wrapped = ClawGraphOpenAIClient(client)

        result = wrapped.chat.completions.create(
            model="gpt-test",
            messages=[{"role": "user", "content": "hello"}],
        )
        self.assertTrue(result["extra_headers"]["x-clawgraph-session-id"].startswith("sess_"))

        with self.assertRaisesRegex(ValueError, "responses.create"):
            wrapped.responses.create(model="gpt-test", input="hello")

    def test_wrapper_can_emit_semantic_events(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store_uri = f"sqlite:///{db_path}"

            class _ModelHandler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:  # noqa: N802
                    self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    response_body = b'{"choices":[{"message":{"role":"assistant","content":"ok"}}]}'
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

            try:
                upstream, upstream_thread = _start_server(_ModelHandler)
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
                fake_client = _FakeOpenAIClient(base_url=f"http://127.0.0.1:{proxy.server_address[1]}")
                wrapped = ClawGraphOpenAIClient(fake_client, base_url=f"http://127.0.0.1:{proxy.server_address[1]}")
                wrapped.chat.completions.create(
                    model="gpt-test",
                    messages=[{"role": "user", "content": "hello"}],
                )
                semantic_response = wrapped.emit_semantic(
                    kind="retry_declared",
                    payload={
                        "branch_id": "br_retry_wrapper_1",
                        "branch_type": "retry",
                        "status": "succeeded",
                    },
                )
                self.assertEqual(semantic_response.status_code, 202)

                store = SQLiteFactStore(store_uri)
                facts = store.list_facts(wrapped.session.session_id)
                semantic_facts = [fact for fact in facts if fact.kind == "semantic_event"]
                self.assertEqual(len(semantic_facts), 1)
                self.assertEqual(semantic_facts[0].run_id, wrapped.session.run_id)
            finally:
                proxy.shutdown()
                upstream.shutdown()
                proxy.server_close()
                upstream.server_close()
                proxy_thread.join(timeout=2)
                upstream_thread.join(timeout=2)
