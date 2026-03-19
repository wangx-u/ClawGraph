from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from clawgraph.export import export_dataset
from clawgraph.protocol.factories import new_fact_event
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


if __name__ == "__main__":
    unittest.main()
