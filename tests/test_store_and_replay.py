from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawgraph.graph import render_session_replay
from clawgraph.protocol.factories import new_fact_event
from clawgraph.store import SQLiteFactStore


class StoreAndReplayTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
