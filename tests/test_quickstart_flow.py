from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from clawgraph.cli.main import main
from clawgraph.protocol.factories import new_fact_event, new_semantic_event_fact
from clawgraph.store import SQLiteFactStore


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

            self.assertEqual(first["persisted_count"], 4)
            self.assertEqual(first["skipped_duplicates"], 0)
            self.assertEqual(second["persisted_count"], 0)
            self.assertEqual(second["skipped_duplicates"], 4)

    def test_list_readiness_reports_recent_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            first = self._run_cli(
                "bootstrap",
                "openclaw",
                "--store",
                store_uri,
                "--session-id",
                "sess_a",
                "--json",
            )
            second = self._run_cli(
                "bootstrap",
                "openclaw",
                "--store",
                store_uri,
                "--session-id",
                "sess_b",
                "--json",
            )

            payload = self._run_cli(
                "list",
                "readiness",
                "--store",
                store_uri,
                "--builder",
                "preference",
                "--json",
            )
            self.assertEqual(len(payload), 2)
            self.assertEqual(payload[0]["session_id"], second["session_id"])
            self.assertEqual(payload[1]["session_id"], first["session_id"])
            self.assertTrue(payload[0]["builders"][0]["ready"])

    def test_list_readiness_reports_recent_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            first = self._run_cli(
                "bootstrap",
                "openclaw",
                "--store",
                store_uri,
                "--session-id",
                "sess_runs",
                "--run-id",
                "run_1",
                "--json",
            )
            second = self._run_cli(
                "bootstrap",
                "openclaw",
                "--store",
                store_uri,
                "--session-id",
                "sess_runs_2",
                "--run-id",
                "run_2",
                "--json",
            )

            payload = self._run_cli(
                "list",
                "readiness",
                "--store",
                store_uri,
                "--builder",
                "preference",
                "--json",
            )
            self.assertEqual(len(payload), 2)
            self.assertEqual(payload[0]["run_id"], second["run_id"])
            self.assertEqual(payload[1]["run_id"], first["run_id"])

    def test_pipeline_run_dry_run_uses_staged_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            self._seed_retry_session_without_artifacts(
                store_uri=store_uri,
                session_id="sess_pipeline_dry",
                run_id="run_pipeline_dry",
            )

            payload = self._run_cli(
                "pipeline",
                "run",
                "--store",
                store_uri,
                "--session",
                "sess_pipeline_dry",
                "--run-id",
                "run_pipeline_dry",
                "--builder",
                "preference",
                "--template",
                "openclaw-defaults",
                "--dry-run",
                "--json",
            )
            self.assertEqual(payload["bootstrap"]["planned_count"], 4)
            self.assertEqual(payload["bootstrap"]["staged_count"], 4)
            self.assertTrue(payload["readiness"]["builders"][0]["ready"])
            self.assertGreater(payload["export"]["record_count"], 0)
            self.assertFalse(payload["export"]["exported"])

    def test_pipeline_run_persists_and_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
            out_path = Path(tempdir) / "exports" / "pref.jsonl"
            self._seed_retry_session_without_artifacts(
                store_uri=store_uri,
                session_id="sess_pipeline_write",
                run_id="run_pipeline_write",
            )

            payload = self._run_cli(
                "pipeline",
                "run",
                "--store",
                store_uri,
                "--session",
                "sess_pipeline_write",
                "--run-id",
                "run_pipeline_write",
                "--builder",
                "preference",
                "--template",
                "openclaw-defaults",
                "--out",
                str(out_path),
                "--json",
            )
            self.assertEqual(payload["bootstrap"]["persisted_count"], 4)
            self.assertTrue(payload["export"]["exported"])
            self.assertEqual(payload["export"]["exported_count"], 1)
            self.assertTrue(out_path.exists())
            self.assertTrue(out_path.with_name("pref.jsonl.manifest.json").exists())

    def _run_cli(self, *argv: str) -> dict | list:
        buffer = StringIO()
        with patch("sys.argv", ["clawgraph", *argv]), redirect_stdout(buffer):
            return_code = main()
        self.assertEqual(return_code, 0)
        return json.loads(buffer.getvalue())

    def _seed_retry_session_without_artifacts(
        self,
        *,
        store_uri: str,
        session_id: str,
        run_id: str,
    ) -> None:
        store = SQLiteFactStore(store_uri)
        main_request = new_fact_event(
            run_id=run_id,
            session_id=session_id,
            actor="model",
            kind="request_started",
            payload={"path": "/v1/chat/completions"},
            request_id="req_main",
        )
        main_error = new_fact_event(
            run_id=run_id,
            session_id=session_id,
            actor="proxy",
            kind="error_raised",
            payload={"path": "/v1/chat/completions", "status_code": 502},
            request_id="req_main",
            parent_ref=main_request.fact_id,
        )
        retry_request = new_fact_event(
            run_id=run_id,
            session_id=session_id,
            actor="model",
            kind="request_started",
            payload={"path": "/v1/chat/completions"},
            request_id="req_retry",
        )
        retry_declared = new_semantic_event_fact(
            run_id=run_id,
            session_id=session_id,
            semantic_kind="retry_declared",
            fact_ref=retry_request.fact_id,
            payload={
                "request_fact_id": retry_request.fact_id,
                "request_id": "req_retry",
                "parent_request_id": "req_main",
                "branch_id": "br_retry_declared_1",
                "branch_type": "retry",
                "status": "succeeded",
            },
            request_id="req_retry",
        )
        retry_response = new_fact_event(
            run_id=run_id,
            session_id=session_id,
            actor="model",
            kind="response_finished",
            payload={"path": "/v1/chat/completions", "status_code": 200},
            request_id="req_retry",
            parent_ref=retry_request.fact_id,
        )
        for fact in (main_request, main_error, retry_request, retry_declared, retry_response):
            store.append_fact(fact)


if __name__ == "__main__":
    unittest.main()
