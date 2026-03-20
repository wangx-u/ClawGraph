from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clawgraph.bootstrap import bootstrap_openclaw_session
from clawgraph.cli.main import _load_json_argument, _resolve_target_ref
from clawgraph.store import SQLiteFactStore


class CliHelpersTest(unittest.TestCase):
    def test_load_json_argument_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            payload_path = Path(tempdir) / "payload.json"
            payload_path.write_text('{"score": 1}', encoding="utf-8")
            payload = _load_json_argument(f"@{payload_path}", label="artifact payload")
            self.assertEqual(payload["score"], 1)

    def test_resolve_target_ref_shortcuts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            result = bootstrap_openclaw_session(store_uri=store_uri)
            store = SQLiteFactStore(store_uri)

            target_ref, session_id = _resolve_target_ref(
                store=store,
                target_ref="latest-response",
                session_value="latest",
            )
            self.assertEqual(session_id, result.session_id)
            self.assertTrue(target_ref.startswith("fact:"))

            branch_ref, _ = _resolve_target_ref(
                store=store,
                target_ref="latest-succeeded-branch",
                session_value=result.session_id,
            )
            self.assertEqual(branch_ref, "branch:br_retry_declared_1")


if __name__ == "__main__":
    unittest.main()
