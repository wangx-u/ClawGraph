from __future__ import annotations

import json
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error, request

from clawgraph.artifacts import E1_ANNOTATION_ARTIFACT_TYPE, E1_ANNOTATION_KIND
from clawgraph.control_plane.server import ControlPlaneConfig, _build_handler
from clawgraph.curation import freeze_cohort
from clawgraph.evaluation import create_eval_suite_from_cohort, enqueue_feedback
from clawgraph.export import export_dataset
from clawgraph.integrations.logits.manifests import TrainingRequestManifest, save_manifest
from clawgraph.integrations.logits.registry import persist_training_manifest_record
from clawgraph.protocol.factories import new_artifact_record, new_fact_event, new_slice_record
from clawgraph.store import SQLiteFactStore


def _fake_training_executor(manifest: TrainingRequestManifest) -> dict[str, object]:
    return {
        "candidate_model": "mini-control-plane",
        "checkpoint_path": "logits://checkpoint/mini-control-plane",
        "sampler_path": "logits://sampler/mini-control-plane",
        "metadata": {"source": "test-control-plane"},
    }


def _fake_eval_sample(model_descriptor: dict[str, str], case) -> dict[str, object]:
    if model_descriptor["label"] == "candidate":
        return {"text": case.reference_text, "latency_ms": 110.0}
    return {"text": "baseline miss", "latency_ms": 180.0}


class ControlPlaneServerTest(unittest.TestCase):
    def test_feedback_write_requires_token_and_binds_actor(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri, store, manifest_dir, feedback_id, _request_id = self._seed_store(Path(tempdir))
            with self._running_server(
                    store_uri=store_uri,
                    manifest_dir=manifest_dir,
                    auth_token="secret-token",
                    actor="review.bot",
                ) as base_url:
                response = self._request_json(
                    base_url=base_url,
                    path="/api/dashboard/feedback/resolve",
                    payload={
                        "feedbackId": feedback_id,
                        "status": "resolved",
                        "reviewer": "forged-user",
                        "note": "resolved from UI",
                    },
                    expected_status=401,
                )
            self.assertEqual(response["error"], "control-plane authentication failed")

            with self._running_server(
                store_uri=store_uri,
                manifest_dir=manifest_dir,
                auth_token="secret-token",
                actor="review.bot",
            ) as base_url:
                payload = self._request_json(
                    base_url=base_url,
                    path="/api/dashboard/feedback/resolve",
                    payload={
                        "feedbackId": feedback_id,
                        "status": "reviewed",
                        "reviewer": "forged-user",
                        "note": "resolved from UI",
                    },
                    token="secret-token",
                )

            self.assertEqual(payload["reviewer"], "review.bot")
            updated = store.get_feedback_queue_item(feedback_id)
            self.assertIsNotNone(updated)
            self.assertEqual(updated.status, "reviewed")
            self.assertEqual(updated.metadata.get("reviewer"), "review.bot")
            self.assertEqual(updated.metadata.get("resolution_note"), "resolved from UI")

    def test_control_plane_can_submit_evaluate_and_handoff_training_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri, store, manifest_dir, _feedback_id, request_id = self._seed_store(Path(tempdir))

            with self._running_server(
                store_uri=store_uri,
                manifest_dir=manifest_dir,
                auth_token="secret-token",
                actor="training.bot",
            ) as base_url:
                submit_payload = self._request_json(
                    base_url=base_url,
                    path="/api/training/submit",
                    payload={
                        "requestId": request_id,
                        "executorRef": "tests.test_control_plane:_fake_training_executor",
                    },
                    token="secret-token",
                )
                candidate_id = submit_payload["candidate"]["candidate_model_id"]

                evaluate_payload = self._request_json(
                    base_url=base_url,
                    path="/api/training/evaluate",
                    payload={
                        "candidateId": candidate_id,
                        "sampleRef": "tests.test_control_plane:_fake_eval_sample",
                    },
                    token="secret-token",
                )
                promotion_id = evaluate_payload["promotion"]["promotion_decision_id"]

                handoff_payload = self._request_json(
                    base_url=base_url,
                    path="/api/training/handoff",
                    payload={
                        "candidateId": candidate_id,
                        "promotionDecisionId": promotion_id,
                    },
                    token="secret-token",
                )

                bundle_payload = self._request_json(
                    base_url=base_url,
                    path="/api/dashboard/bundle",
                    method="GET",
                )

            self.assertEqual(submit_payload["candidate"]["candidate_model"], "mini-control-plane")
            self.assertEqual(evaluate_payload["scorecard"]["verdict"], "pass")
            self.assertEqual(handoff_payload["handoff"]["decision"], "promote")
            self.assertTrue(bundle_payload["meta"]["supportsMutations"])
            self.assertEqual(bundle_payload["meta"]["actor"], "training.bot")
            self.assertEqual(bundle_payload["bundle"]["trainingRegistrySummary"]["requestCount"], 1)
            self.assertEqual(bundle_payload["bundle"]["trainingRegistrySummary"]["candidateCount"], 1)
            self.assertEqual(bundle_payload["bundle"]["trainingRegistrySummary"]["evalExecutionCount"], 1)
            self.assertEqual(bundle_payload["bundle"]["trainingRegistrySummary"]["handoffCount"], 1)
            self.assertEqual(len(store.list_training_assets(asset_kind="logits_training_request")), 1)
            self.assertEqual(len(store.list_training_assets(asset_kind="logits_model_candidate")), 1)
            self.assertEqual(len(store.list_training_assets(asset_kind="logits_eval_execution")), 1)
            self.assertEqual(len(store.list_training_assets(asset_kind="logits_router_handoff")), 1)

    def _seed_store(
        self,
        tempdir: Path,
    ) -> tuple[str, SQLiteFactStore, str, str, str]:
        store_uri = f"sqlite:///{tempdir / 'facts.db'}"
        store = SQLiteFactStore(store_uri)
        manifest_dir = tempdir / "manifests"
        manifest_dir.mkdir(parents=True, exist_ok=True)

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
        self._append_annotated_run(
            store=store,
            session_id="session_train",
            run_id="run_train",
            prompt="fix training task",
            response_text="train response",
            task_instance_key="task-train",
            template_hash="tmpl-train",
        )
        self._append_annotated_run(
            store=store,
            session_id="session_eval",
            run_id="run_eval",
            prompt="fix eval task",
            response_text="eval response",
            task_instance_key="task-eval",
            template_hash="tmpl-eval",
        )

        feedback = enqueue_feedback(
            store=store,
            slice_id="slice.capture",
            source="auto_review",
            target_ref="run:run_train",
            reason="needs_human_review",
            payload={"session_id": "session_train", "run_id": "run_train"},
        )

        training = freeze_cohort(
            store=store,
            slice_id="slice.capture",
            name="control-plane-train",
            run_id="run_train",
        )
        out_path = tempdir / "train.sft.jsonl"
        export_dataset(
            store_uri=store_uri,
            builder="sft",
            cohort_id=training.cohort.cohort_id,
            out=out_path,
        )
        snapshot = store.list_dataset_snapshots(cohort_id=training.cohort.cohort_id)[0]

        evaluation = freeze_cohort(
            store=store,
            slice_id="slice.capture",
            name="control-plane-eval",
            run_id="run_eval",
            purpose="evaluation",
        )
        suite = create_eval_suite_from_cohort(
            store=store,
            slice_id="slice.capture",
            suite_kind="offline_test",
            cohort_id=evaluation.cohort.cohort_id,
            dataset_snapshot_id=snapshot.dataset_snapshot_id,
            name="control-plane-offline",
        )

        training_request = TrainingRequestManifest(
            recipe_family="sft",
            recipe_name="supervised.chat_sl",
            base_model="teacher-e2e",
            dataset_snapshot_id=snapshot.dataset_snapshot_id,
            dataset_builder=snapshot.builder,
            eval_suite_id=suite.eval_suite_id,
            input_path=str(out_path),
            log_path=str(manifest_dir / "runs" / "control-plane-sft"),
        )
        destination = save_manifest(training_request, manifest_dir / "request.json")
        persist_training_manifest_record(
            manifest=training_request,
            store=store,
            manifest_path=str(destination),
        )

        return (
            store_uri,
            store,
            str(manifest_dir),
            feedback.feedback_id,
            training_request.training_request_id,
        )

    def _append_annotated_run(
        self,
        *,
        store: SQLiteFactStore,
        session_id: str,
        run_id: str,
        prompt: str,
        response_text: str,
        task_instance_key: str,
        template_hash: str,
    ) -> None:
        request_fact = new_fact_event(
            run_id=run_id,
            session_id=session_id,
            actor="model",
            kind="request_started",
            payload={
                "path": "/v1/chat/completions",
                "json": {"messages": [{"role": "user", "content": prompt}]},
            },
            request_id=f"req_{run_id}",
        )
        response_fact = new_fact_event(
            run_id=run_id,
            session_id=session_id,
            actor="model",
            kind="response_finished",
            payload={
                "path": "/v1/chat/completions",
                "status_code": 200,
                "json": {
                    "choices": [
                        {"message": {"role": "assistant", "content": response_text}}
                    ]
                },
            },
            request_id=f"req_{run_id}",
            parent_ref=request_fact.fact_id,
        )
        annotation = new_artifact_record(
            artifact_type=E1_ANNOTATION_ARTIFACT_TYPE,
            target_ref=f"run:{run_id}",
            producer="taxonomy.v1",
            payload={
                "annotation_kind": E1_ANNOTATION_KIND,
                "task_family": "captured_agent_task",
                "task_type": "generic_proxy_capture",
                "task_template_hash": template_hash,
                "task_instance_key": task_instance_key,
                "verifier_name": "judge-v1",
                "verifier_score": 0.95,
                "quality_confidence": 0.97,
                "taxonomy_version": "taxonomy.v1",
                "annotation_version": "e1.v1",
                "source_channel": "captured",
            },
            session_id=session_id,
            run_id=run_id,
            confidence=0.97,
        )
        store.append_facts([request_fact, response_fact])
        store.append_artifact(annotation)

    def _start_server(
        self,
        *,
        store_uri: str,
        manifest_dir: str,
        auth_token: str,
        actor: str,
    ) -> tuple[str, ThreadingHTTPServer, threading.Thread]:
        config = ControlPlaneConfig(
            host="127.0.0.1",
            port=0,
            store_uri=store_uri,
            manifest_dir=manifest_dir,
            auth_token=auth_token,
            actor=actor,
        )
        server = ThreadingHTTPServer((config.host, 0), _build_handler(config))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        return f"http://{host}:{port}", server, thread

    def _request_json(
        self,
        *,
        base_url: str,
        path: str,
        method: str = "POST",
        payload: dict[str, object] | None = None,
        token: str | None = None,
        expected_status: int = 200,
    ) -> dict[str, object]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = request.Request(
            f"{base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(req) as response:  # noqa: S310
                status = response.status
                text = response.read().decode("utf-8")
        except error.HTTPError as exc:
            status = exc.code
            text = exc.read().decode("utf-8")
        self.assertEqual(status, expected_status)
        return json.loads(text)

    @contextmanager
    def _running_server(
        self,
        *,
        store_uri: str,
        manifest_dir: str,
        auth_token: str,
        actor: str,
    ):
        base_url, server, thread = self._start_server(
            store_uri=store_uri,
            manifest_dir=manifest_dir,
            auth_token=auth_token,
            actor=actor,
        )
        try:
            yield base_url
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
