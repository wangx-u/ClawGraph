from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawgraph.bootstrap import bootstrap_openclaw_session
from clawgraph.export import build_dataset_readiness_summary
from clawgraph.store import SQLiteFactStore


class BootstrapTest(unittest.TestCase):
    def test_bootstrap_openclaw_session_is_export_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            result = bootstrap_openclaw_session(store_uri=store_uri)
            store = SQLiteFactStore(store_uri)

            facts = store.list_facts(result.session_id)
            artifacts = store.list_artifacts(session_id=result.session_id, latest_only=True)
            readiness = build_dataset_readiness_summary(facts, artifacts)
            builders = {builder.builder: builder for builder in readiness.builders}

            self.assertEqual(result.request_ids, ["req_main_1", "req_retry_1"])
            self.assertNotEqual(result.session_id, result.run_id)
            self.assertTrue(builders["sft"].ready)
            self.assertTrue(builders["preference"].ready)
            self.assertTrue(builders["binary_rl"].ready)

    def test_bootstrap_generates_unique_default_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            first = bootstrap_openclaw_session(store_uri=store_uri)
            second = bootstrap_openclaw_session(store_uri=store_uri)

            self.assertNotEqual(first.session_id, second.session_id)
            self.assertNotEqual(first.run_id, second.run_id)

    def test_bootstrap_rejects_existing_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            bootstrap_openclaw_session(store_uri=store_uri, session_id="sess_fixed")

            with self.assertRaises(ValueError):
                bootstrap_openclaw_session(store_uri=store_uri, session_id="sess_fixed")


if __name__ == "__main__":
    unittest.main()
