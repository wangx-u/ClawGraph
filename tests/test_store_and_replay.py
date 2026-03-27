from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawgraph.graph import render_session_replay
from clawgraph.protocol.factories import new_fact_event
from clawgraph.store import SQLiteFactStore, parse_store_uri


class StoreAndReplayTest(unittest.TestCase):
    def test_parse_store_uri_supports_relative_and_absolute_sqlite_paths(self) -> None:
        self.assertEqual(parse_store_uri("sqlite:///clawgraph.db"), Path("clawgraph.db"))
        self.assertEqual(parse_store_uri("sqlite:///tmp/facts.db"), Path("/tmp/facts.db"))
        self.assertEqual(parse_store_uri("sqlite:////tmp/facts.db"), Path("/tmp/facts.db"))

    def test_append_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)

            request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions", "json": {"messages": []}},
            )
            response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={"path": "/v1/chat/completions", "status_code": 200},
                parent_ref=request.fact_id,
            )

            store.append_fact(request)
            store.append_fact(response)

            self.assertEqual(store.get_latest_session_id(), "session_1")
            facts = store.list_facts("session_1")
            self.assertEqual(len(facts), 2)

            replay = render_session_replay(facts)
            self.assertIn("Session: session_1", replay)
            self.assertIn("request_started", replay)
            self.assertIn("response_finished", replay)
            self.assertIn("Request groups:", replay)

    def test_iter_runs_returns_runs_in_recency_order(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            store = SQLiteFactStore(store_uri)

            first = new_fact_event(
                run_id="run_older",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
            )
            second = new_fact_event(
                run_id="run_newer",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
            )

            store.append_facts([first, second])

            self.assertEqual(list(store.iter_runs(session_id="session_1")), ["run_newer", "run_older"])


if __name__ == "__main__":
    unittest.main()
