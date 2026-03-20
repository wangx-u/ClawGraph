from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from clawgraph.cli.main import main


class QuickstartFlowTest(unittest.TestCase):
    def test_bootstrap_readiness_and_export_dry_run_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"

            bootstrap_payload = self._run_cli(
                "bootstrap",
                "openclaw",
                "--store",
                store_uri,
                "--json",
            )
            self.assertIn("session_id", bootstrap_payload)

            requests_payload = self._run_cli(
                "list",
                "requests",
                "--store",
                store_uri,
                "--session",
                "latest",
                "--json",
            )
            self.assertEqual(len(requests_payload), 2)

            readiness_payload = self._run_cli(
                "readiness",
                "--store",
                store_uri,
                "--session",
                "latest",
                "--builder",
                "preference",
                "--json",
            )
            self.assertEqual(len(readiness_payload["builders"]), 1)
            self.assertTrue(readiness_payload["builders"][0]["ready"])

            export_payload = self._run_cli(
                "export",
                "dataset",
                "--store",
                store_uri,
                "--session",
                "latest",
                "--builder",
                "preference",
                "--dry-run",
                "--json",
            )
            self.assertTrue(export_payload["ready"])
            self.assertEqual(export_payload["record_count"], 1)

    def test_inspect_request_latest_is_session_aware(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"

            first = self._run_cli(
                "bootstrap",
                "openclaw",
                "--store",
                store_uri,
                "--session-id",
                "sess_first",
                "--json",
            )
            self._run_cli(
                "bootstrap",
                "openclaw",
                "--store",
                store_uri,
                "--session-id",
                "sess_second",
                "--json",
            )

            request_payload = self._run_cli(
                "inspect",
                "request",
                "--store",
                store_uri,
                "--session",
                first["session_id"],
                "--request-id",
                "latest",
                "--json",
            )
            self.assertEqual(request_payload["session_id"], "sess_first")

    def test_artifact_bootstrap_skips_duplicates_on_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            bootstrap = self._run_cli(
                "bootstrap",
                "openclaw",
                "--store",
                store_uri,
                "--session-id",
                "sess_bootstrap",
                "--json",
            )

            first = self._run_cli(
                "artifact",
                "bootstrap",
                "--store",
                store_uri,
                "--session",
                bootstrap["session_id"],
                "--template",
                "openclaw-defaults",
                "--json",
            )
            second = self._run_cli(
                "artifact",
                "bootstrap",
                "--store",
                store_uri,
                "--session",
                bootstrap["session_id"],
                "--template",
                "openclaw-defaults",
                "--json",
            )

            self.assertEqual(first["persisted_count"], 3)
            self.assertEqual(first["skipped_duplicates"], 0)
            self.assertEqual(second["persisted_count"], 0)
            self.assertEqual(second["skipped_duplicates"], 3)

    def _run_cli(self, *argv: str) -> dict | list:
        buffer = StringIO()
        with patch("sys.argv", ["clawgraph", *argv]), redirect_stdout(buffer):
            return_code = main()
        self.assertEqual(return_code, 0)
        return json.loads(buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
