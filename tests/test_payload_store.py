from __future__ import annotations

import gzip
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from clawgraph.protocol.factories import new_artifact_record, new_fact_event
from clawgraph.protocol.models import ArtifactRecord, FactEvent
from clawgraph.proxy.payload_store import LocalPayloadStore
from clawgraph.store import SQLiteFactStore


class PayloadStoreTest(unittest.TestCase):
    def test_garbage_collect_skips_unmanaged_files_and_honors_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root_dir = Path(tempdir) / "payloads"
            payload_store = LocalPayloadStore(root_dir=root_dir, store_uri="sqlite:///ignored.db")

            live_ref = payload_store.write_bytes(
                session_id="session_1",
                run_id="run_1",
                request_id="req_live",
                body_kind="response_body",
                request_path="/v1/chat/completions",
                content_type="application/json",
                body=b'{"live":true}',
            )
            orphan_ref = payload_store.write_bytes(
                session_id="session_1",
                run_id="run_1",
                request_id="req_orphan",
                body_kind="response_body",
                request_path="/v1/chat/completions",
                content_type="application/json",
                body=b'{"orphan":true}',
            )
            keep_me = root_dir / "keep-me.txt"
            keep_me.write_text("leave me alone\n", encoding="utf-8")
            temp_sidecar = root_dir / ".tmp-stray.json.gz"
            temp_sidecar.write_bytes(b"not-a-real-sidecar")

            dry_run = payload_store.garbage_collect(
                referenced_body_refs=[live_ref],
                dry_run=True,
                grace_period_seconds=0,
            )
            self.assertEqual(dry_run["would_delete_files"], 1)
            self.assertEqual(dry_run["deleted_files"], 0)
            self.assertTrue(keep_me.exists())
            self.assertTrue(temp_sidecar.exists())
            self.assertTrue(payload_store.resolve_body_path(orphan_ref).exists())

            result = payload_store.garbage_collect(
                referenced_body_refs=[live_ref],
                dry_run=False,
                grace_period_seconds=0,
            )
            self.assertEqual(result["deleted_files"], 1)
            self.assertFalse(payload_store.resolve_body_path(orphan_ref).exists())
            self.assertTrue(payload_store.resolve_body_path(live_ref).exists())
            self.assertTrue(keep_me.exists())
            self.assertTrue(temp_sidecar.exists())

    def test_read_bytes_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root_dir = Path(tempdir) / "payloads"
            outside_path = Path(tempdir) / "outside.json.gz"
            with gzip.open(outside_path, "wb") as handle:
                handle.write(b'{"secret":true}')

            payload_store = LocalPayloadStore(root_dir=root_dir, store_uri="sqlite:///ignored.db")
            with self.assertRaisesRegex(ValueError, "escapes the payload root"):
                payload_store.read_bytes(
                    {
                        "storage": "local_file",
                        "path": str(outside_path),
                        "encoding": "gzip",
                    }
                )

    def test_read_bytes_validates_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root_dir = Path(tempdir) / "payloads"
            payload_store = LocalPayloadStore(root_dir=root_dir, store_uri="sqlite:///ignored.db")
            body_ref = payload_store.write_bytes(
                session_id="session_1",
                run_id="run_1",
                request_id="req_1",
                body_kind="response_body",
                request_path="/v1/chat/completions",
                content_type="application/json",
                body=b'{"ok":true}',
            )

            bad_sha = dict(body_ref)
            bad_sha["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "sha256 mismatch"):
                payload_store.read_bytes(bad_sha)

            bad_size = dict(body_ref)
            bad_size["byte_size"] = 999
            with self.assertRaisesRegex(ValueError, "size mismatch"):
                payload_store.read_bytes(bad_size)


class ProtocolValidationTest(unittest.TestCase):
    def test_factory_validation_rejects_invalid_body_ref(self) -> None:
        with self.assertRaisesRegex(ValueError, "body_ref"):
            new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/chat/completions",
                    "body_ref": "not-a-dict",
                },
            )

        with self.assertRaisesRegex(ValueError, "artifact confidence"):
            new_artifact_record(
                artifact_type="score",
                target_ref="session:session_1",
                producer="judge",
                payload={"score": 1.0},
                confidence=True,
            )

    def test_store_validation_rejects_invalid_records(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = SQLiteFactStore(f"sqlite:///{Path(tempdir) / 'facts.db'}")

            invalid_fact = FactEvent(
                fact_id="fact_invalid",
                schema_version="v1",
                run_id="run_1",
                session_id="session_1",
                timestamp=datetime.now(UTC),
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions", "body_ref": "bad"},
                metadata={},
            )
            with self.assertRaisesRegex(ValueError, "body_ref"):
                store.append_fact(invalid_fact)

            invalid_artifact = ArtifactRecord(
                artifact_id="art_invalid",
                schema_version="v1",
                artifact_type="score",
                target_ref="session:session_1",
                producer="judge",
                payload={"score": 1.0},
                status="active",
                confidence="high",
                metadata={},
            )
            with self.assertRaisesRegex(ValueError, "artifact confidence"):
                store.append_artifact(invalid_artifact)


if __name__ == "__main__":
    unittest.main()
