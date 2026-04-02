from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from clawgraph.artifacts import E1_ANNOTATION_ARTIFACT_TYPE, E1_ANNOTATION_KIND
from clawgraph.curation import freeze_cohort
from clawgraph.export import (
    build_dataset_readiness_summary,
    export_dataset,
    plan_dataset_export,
    register_dataset_builder,
    unregister_dataset_builder,
)
from clawgraph.protocol.factories import new_artifact_record, new_fact_event, new_slice_record
from clawgraph.store import SQLiteFactStore


class ExportDatasetTest(unittest.TestCase):
    def test_builtin_readiness_requires_e1_annotations(self) -> None:
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
                "json": {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
            },
            request_id="req_1",
            parent_ref=request.fact_id,
        )
        score = new_artifact_record(
            artifact_type="score",
            target_ref=f"fact:{response.fact_id}",
            producer="judge-v1",
            payload={"score": 1.0},
            session_id="session_1",
            run_id="run_1",
        )

        missing_annotation = build_dataset_readiness_summary(
            [request, response],
            [score],
            builder="sft",
        )
        self.assertFalse(missing_annotation.builders[0].ready)
        self.assertIn("missing E1 annotations", missing_annotation.builders[0].blockers[0])
        self.assertEqual(missing_annotation.evidence["level"], "E0")

        annotation = new_artifact_record(
            artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
            target_ref="run:run_1",
            producer="taxonomy-v1",
            payload={
                "annotation_kind": E1_ANNOTATION_KIND,
                "task_family": "captured_agent_task",
                "task_type": "generic_proxy_capture",
                "task_template_hash": "tmpl_1",
                "task_instance_key": "run:run_1",
                "verifier_name": "judge-v1",
                "verifier_score": 1.0,
                "quality_confidence": 0.9,
                "taxonomy_version": "taxonomy.v1",
                "annotation_version": "e1.v1",
                "source_channel": "captured",
            },
            session_id="session_1",
            run_id="run_1",
            confidence=0.9,
        )
        ready = build_dataset_readiness_summary(
            [request, response],
            [score, annotation],
            builder="sft",
        )
        self.assertTrue(ready.builders[0].ready)
        self.assertEqual(ready.evidence["level"], "E1")

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

    def test_export_manifest_and_records_include_e1_annotation_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "annotated_sft.jsonl"
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
                    "json": {"choices": [{"message": {"role": "assistant", "content": "hello"}}]},
                },
                request_id="req_1",
                parent_ref=request.fact_id,
            )
            annotation = new_artifact_record(
                artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
                target_ref="run:run_1",
                producer="taxonomy-v1",
                payload={
                    "annotation_kind": E1_ANNOTATION_KIND,
                    "task_family": "captured_agent_task",
                    "task_type": "generic_proxy_capture",
                    "task_template_hash": "tmpl_1",
                    "task_instance_key": "run:run_1",
                    "verifier_name": "judge-v1",
                    "verifier_score": 1.0,
                    "quality_confidence": 0.9,
                    "taxonomy_version": "taxonomy.v1",
                    "annotation_version": "e1.v1",
                    "source_channel": "captured",
                },
                session_id="session_1",
                run_id="run_1",
                confidence=0.9,
            )

            store.append_facts([request, response])
            store.append_artifact(annotation)

            count = export_dataset(
                store_uri=f"sqlite:///{db_path}",
                builder="sft",
                session="session_1",
                out=out_path,
            )
            self.assertEqual(count, 1)
            record = json.loads(out_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["evidence_level"], "E1")
            self.assertEqual(record["annotation"]["task_instance_key"], "run:run_1")
            self.assertIn(record["split"], {"train", "val", "test"})
            manifest = json.loads(
                out_path.with_name(f"{out_path.name}.manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["evidence"]["level"], "E1")
            self.assertEqual(manifest["evidence"]["annotated_runs"], 1)
            self.assertEqual(record["dataset_snapshot_id"], manifest["dataset_snapshot_id"])
            self.assertEqual(record["dataset_recipe_id"], manifest["dataset_recipe_id"])
            self.assertIn("split", manifest)
            snapshots = store.list_dataset_snapshots(builder="sft")
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(
                snapshots[0].dataset_snapshot_id,
                manifest["dataset_snapshot_id"],
            )

    def test_export_dataset_from_cohort_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "cohort_sft.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")
            store.put_slice(
                new_slice_record(
                    slice_id="slice.capture",
                    task_family="captured_agent_task",
                    task_type="generic_proxy_capture",
                    taxonomy_version="taxonomy.v1",
                    sample_unit="run",
                    verifier_contract="judge-v1",
                    risk_level="medium",
                    default_use="training_candidate",
                    owner="ml-team",
                )
            )
            for run_id, session_id, task_instance_key in (
                ("run_1", "session_1", "task-1"),
                ("run_2", "session_2", "task-2"),
            ):
                request = new_fact_event(
                    run_id=run_id,
                    session_id=session_id,
                    actor="model",
                    kind="request_started",
                    payload={
                        "path": "/v1/chat/completions",
                        "json": {"messages": [{"role": "user", "content": run_id}]},
                    },
                    request_id=f"req_{run_id}",
                )
                response = new_fact_event(
                    run_id=run_id,
                    session_id=session_id,
                    actor="model",
                    kind="response_finished",
                    payload={
                        "path": "/v1/chat/completions",
                        "status_code": 200,
                        "json": {
                            "choices": [
                                {"message": {"role": "assistant", "content": f"ok {run_id}"}}
                            ]
                        },
                    },
                    request_id=f"req_{run_id}",
                    parent_ref=request.fact_id,
                )
                annotation = new_artifact_record(
                    artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
                    target_ref=f"run:{run_id}",
                    producer="taxonomy-v1",
                    payload={
                        "annotation_kind": E1_ANNOTATION_KIND,
                        "task_family": "captured_agent_task",
                        "task_type": "generic_proxy_capture",
                        "task_template_hash": f"tmpl_{run_id}",
                        "task_instance_key": task_instance_key,
                        "verifier_name": "judge-v1",
                        "verifier_score": 1.0,
                        "quality_confidence": 0.9,
                        "taxonomy_version": "taxonomy.v1",
                        "annotation_version": "e1.v1",
                        "source_channel": "captured",
                    },
                    session_id=session_id,
                    run_id=run_id,
                    confidence=0.9,
                )
                store.append_facts([request, response])
                store.append_artifact(annotation)

            cohort = freeze_cohort(
                store=store,
                slice_id="slice.capture",
                name="capture-train",
            )

            count = export_dataset(
                store_uri=f"sqlite:///{db_path}",
                builder="sft",
                cohort_id=cohort.cohort.cohort_id,
                out=out_path,
            )
            self.assertEqual(count, 2)
            rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({row["cohort_id"] for row in rows}, {cohort.cohort.cohort_id})
            manifest = json.loads(
                out_path.with_name(f"{out_path.name}.manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["cohort_id"], cohort.cohort.cohort_id)
            self.assertEqual(set(manifest["source_run_ids"]), {"run_1", "run_2"})
            snapshots = store.list_dataset_snapshots(cohort_id=cohort.cohort.cohort_id)
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(
                snapshots[0].dataset_snapshot_id,
                manifest["dataset_snapshot_id"],
            )

    def test_cohort_export_uses_frozen_artifact_view(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "frozen_view.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")
            store.put_slice(
                new_slice_record(
                    slice_id="slice.capture",
                    task_family="captured_agent_task",
                    task_type="generic_proxy_capture",
                    taxonomy_version="taxonomy.v1",
                    sample_unit="run",
                    verifier_contract="judge-v1",
                    risk_level="medium",
                    default_use="training_candidate",
                    owner="ml-team",
                )
            )
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
                    "json": {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
                },
                request_id="req_1",
                parent_ref=request.fact_id,
            )
            annotation_v1 = new_artifact_record(
                artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
                target_ref="run:run_1",
                producer="taxonomy-v1",
                payload={
                    "annotation_kind": E1_ANNOTATION_KIND,
                    "task_family": "captured_agent_task",
                    "task_type": "generic_proxy_capture",
                    "task_template_hash": "tmpl_1",
                    "task_instance_key": "task-1",
                    "verifier_name": "judge-v1",
                    "verifier_score": 0.9,
                    "quality_confidence": 0.95,
                    "taxonomy_version": "taxonomy.v1",
                    "annotation_version": "e1.v1",
                    "source_channel": "captured",
                },
                session_id="session_1",
                run_id="run_1",
                confidence=0.95,
            )
            store.append_facts([request, response])
            store.append_artifact(annotation_v1)

            cohort = freeze_cohort(
                store=store,
                slice_id="slice.capture",
                name="capture-train",
            )

            store.append_artifact(
                new_artifact_record(
                    artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
                    target_ref="run:run_1",
                    producer="taxonomy-v1",
                    payload={
                        "annotation_kind": E1_ANNOTATION_KIND,
                        "task_family": "captured_agent_task",
                        "task_type": "generic_proxy_capture",
                        "task_template_hash": "tmpl_1",
                        "task_instance_key": "task-1",
                        "verifier_name": "judge-v2",
                        "verifier_score": 1.0,
                        "quality_confidence": 1.0,
                        "taxonomy_version": "taxonomy.v1",
                        "annotation_version": "e1.v2",
                        "source_channel": "captured",
                    },
                    session_id="session_1",
                    run_id="run_1",
                    confidence=1.0,
                    supersedes_artifact_id=annotation_v1.artifact_id,
                )
            )

            export_dataset(
                store_uri=f"sqlite:///{db_path}",
                builder="sft",
                cohort_id=cohort.cohort.cohort_id,
                out=out_path,
            )
            record = json.loads(out_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["annotation"]["annotation_version"], "e1.v1")

    def test_multi_session_cohort_export_uses_run_specific_session_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "multi_session.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")
            store.put_slice(
                new_slice_record(
                    slice_id="slice.capture",
                    task_family="captured_agent_task",
                    task_type="generic_proxy_capture",
                    taxonomy_version="taxonomy.v1",
                    sample_unit="run",
                    verifier_contract="judge-v1",
                    risk_level="medium",
                    default_use="training_candidate",
                    owner="ml-team",
                )
            )
            for session_id, run_id, task_instance_key, annotation_version in (
                ("session_1", "run_1", "task-1", "e1.s1"),
                ("session_2", "run_2", "task-2", "e1.s2"),
            ):
                request = new_fact_event(
                    run_id=run_id,
                    session_id=session_id,
                    actor="model",
                    kind="request_started",
                    payload={
                        "path": "/v1/chat/completions",
                        "json": {"messages": [{"role": "user", "content": run_id}]},
                    },
                    request_id=f"req_{run_id}",
                )
                response = new_fact_event(
                    run_id=run_id,
                    session_id=session_id,
                    actor="model",
                    kind="response_finished",
                    payload={
                        "path": "/v1/chat/completions",
                        "status_code": 200,
                        "json": {
                            "choices": [
                                {"message": {"role": "assistant", "content": f"ok {run_id}"}}
                            ]
                        },
                    },
                    request_id=f"req_{run_id}",
                    parent_ref=request.fact_id,
                )
                store.append_facts([request, response])
                store.append_artifact(
                    new_artifact_record(
                        artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
                        target_ref=f"session:{session_id}",
                        producer="taxonomy-v1",
                        payload={
                            "annotation_kind": E1_ANNOTATION_KIND,
                            "task_family": "captured_agent_task",
                            "task_type": "generic_proxy_capture",
                            "task_template_hash": f"tmpl_{session_id}",
                            "task_instance_key": task_instance_key,
                            "verifier_name": "judge-v1",
                            "verifier_score": 0.9,
                            "quality_confidence": 0.95,
                            "taxonomy_version": "taxonomy.v1",
                            "annotation_version": annotation_version,
                            "source_channel": "captured",
                        },
                        session_id=session_id,
                        confidence=0.95,
                    )
                )

            cohort = freeze_cohort(
                store=store,
                slice_id="slice.capture",
                name="capture-train",
            )
            export_dataset(
                store_uri=f"sqlite:///{db_path}",
                builder="sft",
                cohort_id=cohort.cohort.cohort_id,
                out=out_path,
            )
            rows = [
                json.loads(line)
                for line in out_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            by_run = {row["run_id"]: row for row in rows}
            self.assertEqual(by_run["run_1"]["annotation"]["annotation_version"], "e1.s1")
            self.assertEqual(by_run["run_1"]["annotation"]["task_instance_key"], "task-1")
            self.assertEqual(by_run["run_2"]["annotation"]["annotation_version"], "e1.s2")
            self.assertEqual(by_run["run_2"]["annotation"]["task_instance_key"], "task-2")

    def test_cohort_export_blocks_incompatible_builder_sample_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store = SQLiteFactStore(f"sqlite:///{db_path}")
            store.put_slice(
                new_slice_record(
                    slice_id="slice.capture",
                    task_family="captured_agent_task",
                    task_type="generic_proxy_capture",
                    taxonomy_version="taxonomy.v1",
                    sample_unit="run",
                    verifier_contract="judge-v1",
                    risk_level="medium",
                    default_use="training_candidate",
                    owner="ml-team",
                )
            )

            main_request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/chat/completions",
                    "json": {"messages": [{"role": "user", "content": "hi"}]},
                },
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
            annotation = new_artifact_record(
                artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
                target_ref="run:run_1",
                producer="taxonomy-v1",
                payload={
                    "annotation_kind": E1_ANNOTATION_KIND,
                    "task_family": "captured_agent_task",
                    "task_type": "generic_proxy_capture",
                    "task_template_hash": "tmpl_1",
                    "task_instance_key": "task-1",
                    "verifier_name": "judge-v1",
                    "verifier_score": 0.9,
                    "quality_confidence": 0.95,
                    "taxonomy_version": "taxonomy.v1",
                    "annotation_version": "e1.v1",
                    "source_channel": "captured",
                },
                session_id="session_1",
                run_id="run_1",
                confidence=0.95,
            )
            preference = new_artifact_record(
                artifact_type="preference",
                target_ref="session:session_1",
                producer="judge-v1",
                payload={"chosen": "br_retry_1", "rejected": "br_main"},
                session_id="session_1",
                run_id="run_1",
            )

            store.append_facts([main_request, main_error, retry_request, retry_response])
            store.append_artifact(annotation)
            store.append_artifact(preference)

            cohort = freeze_cohort(
                store=store,
                slice_id="slice.capture",
                name="capture-train",
            )
            plan = plan_dataset_export(
                store_uri=f"sqlite:///{db_path}",
                builder="preference",
                cohort_id=cohort.cohort.cohort_id,
            )
            self.assertIn(
                "builder sample_unit is incompatible with cohort slice contract",
                " ".join(plan.blockers),
            )

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

    def test_export_sft_builder_keeps_responses_tool_output_context(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "responses_tool_output_sft.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/responses",
                    "json": {
                        "input": [
                            {"role": "user", "content": "What is 2+2?"},
                            {
                                "type": "function_call_output",
                                "call_id": "call_calc_1",
                                "name": "calculator",
                                "output": "4",
                            },
                        ],
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
                    "json": {"output_text": "The answer is 4."},
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
            self.assertEqual(record["messages"][1]["role"], "tool")
            self.assertEqual(record["messages"][1]["content"], "4")
            self.assertEqual(record["messages"][1]["tool_call_id"], "call_calc_1")
            self.assertEqual(record["completion"]["content"], "The answer is 4.")

    def test_export_sft_builder_from_stream_summary_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "stream_sft.jsonl"
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
                        "stream": True,
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
                    "streamed": True,
                    "json": {
                        "choices": [
                            {"message": {"role": "assistant", "content": "hello from stream"}}
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
            self.assertEqual(record["messages"][-1]["content"], "hello from stream")

    def test_export_sft_builder_uses_canonical_tool_call_message(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "tool_call_sft.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/chat/completions",
                    "json": {
                        "messages": [{"role": "user", "content": "look this up"}],
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
                    "canonical": {
                        "assistant_message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup",
                                        "arguments": '{"q":"agent rl"}',
                                    },
                                }
                            ],
                        }
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
            tool_calls = record["messages"][-1]["tool_calls"]
            self.assertEqual(tool_calls[0]["function"]["name"], "lookup")
            self.assertEqual(tool_calls[0]["function"]["arguments"], '{"q":"agent rl"}')

    def test_export_sft_builder_from_spilled_compact_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "spilled_sft.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/chat/completions",
                    "capture_truncated": True,
                    "body_ref": {
                        "storage": "local_file",
                        "relative_path": "session_1/run_1/req_1/request_body.json.gz",
                        "encoding": "gzip",
                        "content_type": "application/json",
                        "byte_size": 4096,
                        "compressed_size": 1024,
                        "sha256": "0" * 64,
                    },
                    "input_messages": [{"role": "user", "content": "hi from spill"}],
                    "request_fingerprint": '{"messages": [{"content": "hi from spill", "role": "user"}]}',
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
                    "capture_truncated": True,
                    "body_ref": {
                        "storage": "local_file",
                        "relative_path": "session_1/run_1/req_1/response_body.json.gz",
                        "encoding": "gzip",
                        "content_type": "application/json",
                        "byte_size": 8192,
                        "compressed_size": 2048,
                        "sha256": "1" * 64,
                    },
                    "canonical": {
                        "assistant_message": {
                            "role": "assistant",
                            "content": "hello from spill",
                        }
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
            self.assertEqual(record["messages"][0]["content"], "hi from spill")
            self.assertEqual(record["messages"][-1]["content"], "hello from spill")

    def test_export_sft_builder_from_responses_function_call_output(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "responses_tool_call_sft.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/responses",
                    "json": {"input": "look this up"},
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
                                "id": "fc_1",
                                "type": "function_call",
                                "name": "lookup",
                                "arguments": '{"q":"agent rl"}',
                                "call_id": "call_1",
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
            tool_calls = record["messages"][-1]["tool_calls"]
            self.assertEqual(tool_calls[0]["function"]["name"], "lookup")
            self.assertEqual(tool_calls[0]["function"]["arguments"], '{"q":"agent rl"}')

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
            self.assertEqual(record["run_id"], "run_1")

    def test_export_preference_skips_mismatched_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            out_path = Path(tempdir) / "preference.jsonl"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            main_request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/chat/completions",
                    "json": {"messages": [{"role": "user", "content": "task A"}]},
                },
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
                payload={
                    "path": "/v1/chat/completions",
                    "json": {
                        "messages": [{"role": "user", "content": "completely different task B"}]
                    },
                },
                request_id="req_retry",
            )
            retry_response = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={
                    "path": "/v1/chat/completions",
                    "status_code": 200,
                    "json": {
                        "choices": [
                            {"message": {"role": "assistant", "content": "result B"}}
                        ]
                    },
                },
                request_id="req_retry",
                parent_ref=retry_request.fact_id,
            )

            for fact in (main_request, main_error, retry_request, retry_response):
                store.append_fact(fact)

            count = export_dataset(
                store_uri=f"sqlite:///{db_path}",
                builder="preference",
                session="session_1",
                out=out_path,
            )
            self.assertEqual(count, 0)
            manifest = json.loads(
                out_path.with_name(f"{out_path.name}.manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["record_count"], 0)

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
            self.assertEqual(record["run_id"], "run_1")
            self.assertEqual(record["reward"], 0.75)
            self.assertEqual(record["target"]["fact_id"], response.fact_id)
            self.assertIn("trajectory", record["target"])
            self.assertEqual(record["supervision"]["reward"], 0.75)
            self.assertEqual(record["lineage"]["builder"], "binary_rl")

    def test_export_binary_rl_builder_resolves_explicit_run_target(self) -> None:
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
                target_ref="run:run_1",
                producer="judge-v1",
                payload={"score": 1.0},
                session_id="session_1",
                run_id="run_1",
                confidence=0.9,
            )

            store.append_facts([request, response])
            store.append_artifact(score)

            count = export_dataset(
                store_uri=f"sqlite:///{db_path}",
                builder="binary_rl",
                session="session_1",
                out=out_path,
            )
            self.assertEqual(count, 1)
            record = json.loads(out_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["target"]["type"], "run")
            self.assertEqual(record["target"]["run_id"], "run_1")

    def test_plan_dataset_export_defaults_to_latest_run_in_session(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            first_request = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_run_1",
            )
            first_error = new_fact_event(
                run_id="run_1",
                session_id="session_1",
                actor="proxy",
                kind="error_raised",
                payload={"path": "/v1/chat/completions", "status_code": 502},
                request_id="req_run_1",
                parent_ref=first_request.fact_id,
            )
            second_request = new_fact_event(
                run_id="run_2",
                session_id="session_1",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/chat/completions",
                    "json": {"messages": [{"role": "user", "content": "hi"}]},
                },
                request_id="req_run_2",
            )
            second_response = new_fact_event(
                run_id="run_2",
                session_id="session_1",
                actor="model",
                kind="response_finished",
                payload={
                    "path": "/v1/chat/completions",
                    "status_code": 200,
                    "json": {"choices": [{"message": {"role": "assistant", "content": "hello"}}]},
                },
                request_id="req_run_2",
                parent_ref=second_request.fact_id,
            )
            for fact in (first_request, first_error, second_request, second_response):
                store.append_fact(fact)

            plan = plan_dataset_export(
                store_uri=f"sqlite:///{db_path}",
                builder="sft",
                session="session_1",
            )
            self.assertEqual(plan.run_id, "run_2")
            self.assertEqual(plan.record_count, 1)
            self.assertEqual(plan.manifest["source_run_ids"], ["run_2"])

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
            store.append_artifact(
                new_artifact_record(
                    artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
                    target_ref="run:run_1",
                    producer="taxonomy-v1",
                    payload={
                        "annotation_kind": E1_ANNOTATION_KIND,
                        "task_family": "captured_agent_task",
                        "task_type": "generic_proxy_capture",
                        "task_template_hash": "tmpl_1",
                        "task_instance_key": "run:run_1",
                        "verifier_name": "judge-v1",
                        "verifier_score": 1.0,
                        "quality_confidence": 0.9,
                        "taxonomy_version": "taxonomy.v1",
                        "annotation_version": "e1.v1",
                        "source_channel": "captured",
                    },
                    session_id="session_1",
                    run_id="run_1",
                    confidence=0.9,
                )
            )

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

    def test_plan_dataset_export_explicit_run_id_ignores_latest_session_default(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "facts.db"
            store = SQLiteFactStore(f"sqlite:///{db_path}")

            first_request = new_fact_event(
                run_id="run_a",
                session_id="sess_a",
                actor="model",
                kind="request_started",
                payload={
                    "path": "/v1/chat/completions",
                    "json": {"messages": [{"role": "user", "content": "alpha"}]},
                },
                request_id="req_a",
            )
            first_response = new_fact_event(
                run_id="run_a",
                session_id="sess_a",
                actor="model",
                kind="response_finished",
                payload={
                    "path": "/v1/chat/completions",
                    "status_code": 200,
                    "json": {"choices": [{"message": {"role": "assistant", "content": "A"}}]},
                },
                request_id="req_a",
                parent_ref=first_request.fact_id,
            )
            second_request = new_fact_event(
                run_id="run_b",
                session_id="sess_b",
                actor="model",
                kind="request_started",
                payload={"path": "/v1/chat/completions"},
                request_id="req_b",
            )
            store.append_facts([first_request, first_response, second_request])

            plan = plan_dataset_export(
                store_uri=f"sqlite:///{db_path}",
                builder="sft",
                session="latest",
                run_id="run_a",
            )

            self.assertEqual(plan.session_id, "sess_a")
            self.assertEqual(plan.run_id, "run_a")
            self.assertEqual(plan.record_count, 1)

    def test_custom_dataset_builder_integrates_with_export_and_readiness(self) -> None:
        class CustomDatasetBuilder:
            name = "custom_eval"
            aliases = ("custom-eval",)

            def build_records(self, *, facts, artifacts, context=None):  # noqa: ANN001
                del artifacts
                return [
                    {
                        "session_id": context.session_id if context is not None else None,
                        "run_id": context.run_id if context is not None else None,
                        "fact_count": len(facts),
                    }
                ]

            def blockers(self, *, facts, artifacts, records, context=None):  # noqa: ANN001
                del artifacts, context
                if facts and records:
                    return []
                return ["no facts found"]

        register_dataset_builder(CustomDatasetBuilder(), replace=True)
        try:
            facts = [
                new_fact_event(
                    run_id="run_1",
                    session_id="session_1",
                    actor="model",
                    kind="request_started",
                    payload={"path": "/v1/chat/completions"},
                    request_id="req_1",
                )
            ]
            readiness = build_dataset_readiness_summary(facts, [], builder="custom-eval")
            self.assertEqual(readiness.builders[0].builder, "custom_eval")
            self.assertTrue(readiness.builders[0].ready)
            self.assertEqual(readiness.builders[0].predicted_records, 1)

            with tempfile.TemporaryDirectory() as tempdir:
                db_path = Path(tempdir) / "facts.db"
                store = SQLiteFactStore(f"sqlite:///{db_path}")
                store.append_facts(facts)
                plan = plan_dataset_export(
                    store_uri=f"sqlite:///{db_path}",
                    builder="custom-eval",
                    session="session_1",
                    run_id="run_1",
                )
                self.assertEqual(plan.builder, "custom_eval")
                self.assertEqual(plan.records[0]["fact_count"], 1)
                self.assertEqual(plan.records[0]["run_id"], "run_1")
        finally:
            unregister_dataset_builder("custom_eval")


if __name__ == "__main__":
    unittest.main()
