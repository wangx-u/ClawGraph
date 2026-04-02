from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from clawgraph.artifacts import E1_ANNOTATION_ARTIFACT_TYPE, E1_ANNOTATION_KIND
from clawgraph.curation import freeze_cohort, list_slice_candidates
from clawgraph.protocol.factories import (
    new_artifact_record,
    new_fact_event,
    new_slice_record,
)
from clawgraph.query import ClawGraphQueryService
from clawgraph.store import SQLiteFactStore


def _append_annotated_run(
    store: SQLiteFactStore,
    *,
    session_id: str,
    run_id: str,
    task_instance_key: str,
    task_type: str = "generic_proxy_capture",
    taxonomy_version: str = "taxonomy.v1",
    quality_confidence: float = 0.9,
    verifier_score: float = 0.8,
    target_ref: str | None = None,
    extra_payload: dict[str, object] | None = None,
):
    request = new_fact_event(
        run_id=run_id,
        session_id=session_id,
        actor="model",
        kind="request_started",
        payload={
            "path": "/v1/chat/completions",
            "json": {"messages": [{"role": "user", "content": f"hi {run_id}"}]},
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
            "json": {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        },
        request_id=f"req_{run_id}",
        parent_ref=request.fact_id,
    )
    annotation = new_artifact_record(
        artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
        target_ref=target_ref or f"run:{run_id}",
        producer="taxonomy-v1",
        payload={
            "annotation_kind": E1_ANNOTATION_KIND,
            "task_family": "captured_agent_task",
            "task_type": task_type,
            "task_template_hash": f"tmpl_{run_id}",
            "task_instance_key": task_instance_key,
            "verifier_name": "judge-v1",
            "verifier_score": verifier_score,
            "quality_confidence": quality_confidence,
            "taxonomy_version": taxonomy_version,
            "annotation_version": "e1.v1",
            "source_channel": "captured",
            "difficulty": "medium",
            **(extra_payload or {}),
        },
        session_id=session_id,
        run_id=None if target_ref == f"session:{session_id}" else run_id,
        confidence=quality_confidence,
    )
    store.append_facts([request, response])
    store.append_artifact(annotation)
    return annotation


class CurationTest(unittest.TestCase):
    def test_list_slice_candidates_filters_registered_slice(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = SQLiteFactStore(f"sqlite:///{Path(tempdir) / 'facts.db'}")
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
            kept = _append_annotated_run(
                store,
                session_id="session_1",
                run_id="run_1",
                task_instance_key="task-1",
                quality_confidence=0.92,
                verifier_score=0.81,
            )
            _append_annotated_run(
                store,
                session_id="session_1",
                run_id="run_2",
                task_instance_key="task-2",
                quality_confidence=0.61,
                verifier_score=0.83,
            )
            _append_annotated_run(
                store,
                session_id="session_1",
                run_id="run_3",
                task_instance_key="task-3",
                task_type="other_task_type",
            )

            slice_record, candidates = list_slice_candidates(
                store=store,
                slice_id="slice.capture",
                min_quality_confidence=0.8,
            )

            self.assertEqual(slice_record.slice_id, "slice.capture")
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].run_id, "run_1")
            self.assertEqual(candidates[0].annotation_artifact_id, kept.artifact_id)

    def test_list_slice_candidates_include_session_scoped_annotation_for_explicit_run(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = SQLiteFactStore(f"sqlite:///{Path(tempdir) / 'facts.db'}")
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
            annotation = _append_annotated_run(
                store,
                session_id="session_1",
                run_id="run_1",
                task_instance_key="task-1",
                target_ref="session:session_1",
            )

            _, candidates = list_slice_candidates(
                store=store,
                slice_id="slice.capture",
                run_id="run_1",
            )

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].annotation_artifact_id, annotation.artifact_id)

    def test_freeze_cohort_persists_manifest_and_members(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = SQLiteFactStore(f"sqlite:///{Path(tempdir) / 'facts.db'}")
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
            _append_annotated_run(
                store,
                session_id="session_1",
                run_id="run_1",
                task_instance_key="task-1",
                verifier_score=0.75,
            )
            _append_annotated_run(
                store,
                session_id="session_2",
                run_id="run_2",
                task_instance_key="task-2",
                verifier_score=0.88,
            )

            result = freeze_cohort(
                store=store,
                slice_id="slice.capture",
                name="capture-train",
                min_verifier_score=0.7,
            )

            self.assertEqual(result.cohort.name, "capture-train")
            self.assertEqual(result.cohort.manifest["coverage"]["run_count"], 2)
            self.assertEqual(
                result.cohort.manifest["selection_query"]["min_verifier_score"],
                0.7,
            )
            self.assertEqual(len(result.members), 2)

            service = ClawGraphQueryService(store=store)
            stored_cohort = service.get_cohort(result.cohort.cohort_id)
            self.assertIsNotNone(stored_cohort)
            listed = service.list_cohorts(slice_id="slice.capture")
            self.assertEqual(len(listed), 1)
            members = service.list_cohort_members(result.cohort.cohort_id)
            self.assertEqual(len(members), 2)
            self.assertEqual(
                members[0].metadata["annotation_artifact_ids"][0][:4],
                "art_",
            )

    def test_freeze_cohort_routes_review_and_holdout_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = SQLiteFactStore(f"sqlite:///{Path(tempdir) / 'facts.db'}")
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
            _append_annotated_run(
                store,
                session_id="session_1",
                run_id="run_1",
                task_instance_key="task-1",
                verifier_score=0.9,
                quality_confidence=0.95,
            )
            _append_annotated_run(
                store,
                session_id="session_2",
                run_id="run_2",
                task_instance_key="task-1",
                verifier_score=0.85,
                quality_confidence=0.91,
            )
            _append_annotated_run(
                store,
                session_id="session_3",
                run_id="run_3",
                task_instance_key="task-3",
                task_type="generic_proxy_capture",
                verifier_score=0.3,
                quality_confidence=0.4,
                extra_payload={"new_subtype": True},
            )

            result = freeze_cohort(
                store=store,
                slice_id="slice.capture",
                name="capture-train",
            )

            self.assertEqual(len(result.members), 1)
            self.assertEqual(result.members[0].run_id, "run_1")
            self.assertEqual(len(result.holdout_candidates), 1)
            self.assertEqual(result.holdout_candidates[0].run_id, "run_2")
            self.assertEqual(len(result.review_queue), 1)
            self.assertEqual(result.review_queue[0]["run_id"], "run_3")
            self.assertTrue(result.cohort.manifest["review"]["required"])
            self.assertEqual(result.cohort.manifest["holdout_feed"]["count"], 1)
            self.assertEqual(
                result.cohort.manifest["artifact_view"]["strategy"],
                "frozen_artifact_ids",
            )
            self.assertTrue(result.members[0].metadata["frozen_artifact_ids"])

    def test_list_slice_candidates_backfills_annotation_index_on_reopen(self) -> None:
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
            _append_annotated_run(
                store,
                session_id="session_1",
                run_id="run_1",
                task_instance_key="task-1",
            )

            with sqlite3.connect(db_path) as connection:
                connection.execute("DELETE FROM annotation_index")
                connection.commit()

            reopened = SQLiteFactStore(f"sqlite:///{db_path}")
            _, candidates = list_slice_candidates(
                store=reopened,
                slice_id="slice.capture",
            )
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].run_id, "run_1")


if __name__ == "__main__":
    unittest.main()
