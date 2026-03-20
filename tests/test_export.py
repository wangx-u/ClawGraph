from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from clawgraph.export import export_dataset, plan_dataset_export
from clawgraph.protocol.factories import new_artifact_record, new_fact_event
from clawgraph.store import SQLiteFactStore


class ExportDatasetTest(unittest.TestCase):
    def test_export_sft_builder(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "sft.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/chat/completions",
                    "json": {
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                },
                request_id="req_1",
            )
            response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={
                    "path": "/v1/chat/completions",
                    "status_code": 200,
                    "json": {
                        "choices": [
                            {"message": {"role": "assistant", "content": "hello"}}
                        ]
                    },
                },
                request_id="req_1",
                parent_ref=request.fact_id,
            )

            store.append_fact(request)
            store.append_fact(response)

            count = export_dataset(
                store_uri=f"sqlite:///{db_path}",
                builder="sft",
                session="session_1",
                out=out_path,
            )
            self.assertEqual(count, 1)
            rows = out_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(rows), 1)
            record = json.loads(rows[0])
            self.assertEqual(record["messages"][-1]["content"], "hello")
            self.assertEqual(record["lineage"]["builder"], "sft")
            manifest = json.loads(
                out_path.with_name(f"{out_path.name}.manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["record_count"], 1)

    def test_export_sft_builder_from_responses_api_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "responses_sft.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/responses",
                    "json": {
                        "input": "hi",
                    },
                },
                request_id="req_1",
            )
            response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={
                    "path": "/v1/responses",
                    "status_code": 200,
                    "json": {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "hello"}],
                            }
                        ]
                    },
                },
                request_id="req_1",
                parent_ref=request.fact_id,
            )

            store.append_fact(request)
            store.append_fact(response)

            count = export_dataset(
                store_uri=f"sqlite:///{db_path}",
                builder="sft",
                session="session_1",
                out=out_path,
            )
            self.assertEqual(count, 1)
            record = json.loads(out_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["messages"][0]["content"], "hi")
            self.assertEqual(record["messages"][-1]["content"], "hello")

    def test_export_preference_builder_from_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "preference.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            main_request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_main",
            )
            main_error = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="proxy",
                kind="error_raised",
                payload={"path": "/v1/chat/completions", "status_code": 502},
                request_id="req_main",
                parent_ref=main_request.fact_id,
            )
            retry_request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_retry",
            )
            retry_response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={"path": "/v1/chat/completions", "status_code": 200},
                request_id="req_retry",
                parent_ref=retry_request.fact_id,
            )
            preference = new_artifact_record(
                artifact_type="preference",
                target_ref="session:session_1",
                producer="judge-v1",
                payload={"chosen": "br_retry_1", "rejected": "br_main"},
                session_id="session_1",
                run_id="run_1",
            )

            for fact in (main_request, main_error, retry_request, retry_response):
                store.append_fact(fact)
            store.append_artifact(preference)

            count = export_dataset(
                store_uri=f"sqlite:///{db_path}",
                builder="preference",
                session="session_1",
                out=out_path,
            )
            self.assertEqual(count, 1)
            record = json.loads(out_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["chosen"]["branch_id"], "br_retry_1")
            self.assertEqual(record["rejected"]["branch_id"], "br_main")
            self.assertEqual(record["lineage"]["builder"], "preference")

    def test_export_binary_rl_builder(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "binary_rl.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_1",
            )
            response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={"path": "/v1/chat/completions", "status_code": 200},
                request_id="req_1",
                parent_ref=request.fact_id,
            )
            score = new_artifact_record(
                artifact_type="score",
                target_ref=f"fact:{response.fact_id}",
                producer="judge-v1",
                payload={"score": 0.75},
                session_id="session_1",
                run_id="run_1",
                confidence=0.9,
            )

            store.append_fact(request)
            store.append_fact(response)
            store.append_artifact(score)

            count = export_dataset(
                store_uri=f"sqlite:///{db_path}",
                builder="binary_rl",
                session="session_1",
                out=out_path,
            )
            self.assertEqual(count, 1)
            record = json.loads(out_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["reward"], 0.75)
            self.assertEqual(record["target"]["fact_id"], response.fact_id)
            self.assertEqual(record["lineage"]["builder"], "binary_rl")

    def test_plan_dataset_export_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "sft.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/chat/completions",
                    "json": {"messages": [{"role": "user", "content": "hi"}]},
                },
                request_id="req_1",
            )
            response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={
                    "path": "/v1/chat/completions",
                    "status_code": 200,
                    "json": {
                        "choices": [{"message": {"role": "assistant", "content": "hello"}}]
                    },
                },
                request_id="req_1",
                parent_ref=request.fact_id,
            )
            store.append_fact(request)
            store.append_fact(response)

            plan = plan_dataset_export(
                store_uri=f"sqlite:///{db_path}",
                builder="sft",
                session="session_1",
                out=out_path,
            )
            self.assertTrue(plan.ready)
            self.assertEqual(plan.record_count, 1)
            self.assertEqual(plan.manifest["record_count"], 1)
            self.assertFalse(out_path.exists())


if __name__ == "__main__":
    unittest.main()
