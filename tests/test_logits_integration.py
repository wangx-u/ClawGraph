from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from clawgraph.artifacts import E1_ANNOTATION_ARTIFACT_TYPE, E1_ANNOTATION_KIND
from clawgraph.cli.main import main
from clawgraph.curation import freeze_cohort
from clawgraph.evaluation import create_eval_suite_from_cohort
from clawgraph.export import export_dataset
from clawgraph.integrations.logits import (
    build_training_registry,
    create_router_handoff_manifest,
    evaluate_candidate_on_suite,
    export_preference_snapshot_for_logits,
    export_sft_snapshot_for_logits,
    load_manifest,
    prepare_dpo_training_request,
    prepare_rl_training_request,
    prepare_sft_training_request,
    save_manifest,
    submit_training_request,
)
from clawgraph.integrations.logits.manifests import (
    EvalExecutionManifest,
    ModelCandidateManifest,
    RouterHandoffManifest,
    TrainingRequestManifest,
)
from clawgraph.protocol.factories import new_artifact_record, new_fact_event, new_slice_record
from clawgraph.store import SQLiteFactStore


class LogitsIntegrationTest(unittest.TestCase):
    def _append_annotated_run(
        self,
        *,
        store: SQLiteFactStore,
        run_id: str,
        session_id: str,
        task_instance_key: str,
        template_hash: str,
        user_content: str,
        assistant_content: str,
    ) -> None:
        request = new_fact_event(
            run_id=run_id,
            session_id=session_id,
            actor="model",
            kind="request_started",
            payload={
                "path": "/v1/chat/completions",
                "json": {"messages": [{"role": "user", "content": user_content}]},
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
                        {"message": {"role": "assistant", "content": assistant_content}}
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
                "task_template_hash": template_hash,
                "task_instance_key": task_instance_key,
                "verifier_name": "judge-v1",
                "verifier_score": 0.9,
                "quality_confidence": 0.95,
                "taxonomy_version": "taxonomy.v1",
                "annotation_version": "e1.v1",
                "source_channel": "captured",
                "teacher_model": "deepseek-chat",
            },
            session_id=session_id,
            run_id=run_id,
            confidence=0.95,
        )
        store.append_facts([request, response])
        store.append_artifact(annotation)

    def _seed_store(self, tempdir: str) -> tuple[str, SQLiteFactStore, str, str]:
        store_uri = f"sqlite:///{Path(tempdir) / 'facts.db'}"
        store = SQLiteFactStore(store_uri)
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
            run_id="run_train",
            session_id="session_train",
            task_instance_key="task-train",
            template_hash="tmpl_train",
            user_content="fix task train",
            assistant_content="ok train",
        )
        self._append_annotated_run(
            store=store,
            run_id="run_eval",
            session_id="session_eval",
            task_instance_key="task-eval",
            template_hash="tmpl_eval",
            user_content="fix task eval",
            assistant_content="ok eval",
        )

        training_cohort = freeze_cohort(
            store=store,
            slice_id="slice.capture",
            name="capture-train",
            run_id="run_train",
        )
        train_out = Path(tempdir) / "train.sft.jsonl"
        export_dataset(
            store_uri=store_uri,
            builder="sft",
            cohort_id=training_cohort.cohort.cohort_id,
            out=train_out,
        )
        snapshot = store.list_dataset_snapshots(cohort_id=training_cohort.cohort.cohort_id)[0]

        eval_cohort = freeze_cohort(
            store=store,
            slice_id="slice.capture",
            name="capture-eval",
            run_id="run_eval",
            purpose="evaluation",
        )
        suite = create_eval_suite_from_cohort(
            store=store,
            slice_id="slice.capture",
            suite_kind="offline_test",
            cohort_id=eval_cohort.cohort.cohort_id,
            dataset_snapshot_id=snapshot.dataset_snapshot_id,
            name="capture-offline",
        )
        return store_uri, store, snapshot.dataset_snapshot_id, suite.eval_suite_id

    def _seed_preference_snapshot(self, tempdir: str) -> tuple[str, str]:
        store_uri = f"sqlite:///{Path(tempdir) / 'preference.db'}"
        store = SQLiteFactStore(store_uri)
        main_request = new_fact_event(
            run_id="run_pref",
            session_id="session_pref",
            actor="model",
            kind="request_started",
            payload={
                "path": "/v1/chat/completions",
                "json": {"messages": [{"role": "user", "content": "solve task"}]},
            },
            request_id="req_main",
        )
        main_error = new_fact_event(
            run_id="run_pref",
            session_id="session_pref",
            actor="proxy",
            kind="error_raised",
            payload={"path": "/v1/chat/completions", "status_code": 502},
            request_id="req_main",
            parent_ref=main_request.fact_id,
        )
        retry_request = new_fact_event(
            run_id="run_pref",
            session_id="session_pref",
            actor="model",
            kind="request_started",
            payload={
                "path": "/v1/chat/completions",
                "json": {"messages": [{"role": "user", "content": "solve task"}]},
            },
            request_id="req_retry",
        )
        retry_response = new_fact_event(
            run_id="run_pref",
            session_id="session_pref",
            actor="model",
            kind="response_finished",
            payload={
                "path": "/v1/chat/completions",
                "status_code": 200,
                "json": {
                    "choices": [
                        {"message": {"role": "assistant", "content": "accepted answer"}}
                    ]
                },
            },
            request_id="req_retry",
            parent_ref=retry_request.fact_id,
        )
        preference = new_artifact_record(
            artifact_type="preference",
            target_ref="session:session_pref",
            producer="judge-v1",
            payload={"chosen": "br_retry_1", "rejected": "br_main"},
            session_id="session_pref",
            run_id="run_pref",
        )
        store.append_facts([main_request, main_error, retry_request, retry_response])
        store.append_artifact(preference)
        out = Path(tempdir) / "preference.jsonl"
        export_dataset(
            store_uri=store_uri,
            builder="preference",
            session="session_pref",
            out=out,
        )
        snapshot = store.list_dataset_snapshots(builder="preference")[0]
        return store_uri, snapshot.dataset_snapshot_id

    def test_manifest_roundtrip(self) -> None:
        manifest = TrainingRequestManifest(
            recipe_family="sft",
            recipe_name="supervised.chat_sl",
            base_model="meta-llama/Llama-3.2-1B-Instruct",
            dataset_snapshot_id="ds_1",
            dataset_builder="sft",
            input_path="/tmp/data.jsonl",
            log_path="/tmp/logs",
        )
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "manifest.json"
            save_manifest(manifest, path)
            loaded = load_manifest(path)
            self.assertIsInstance(loaded, TrainingRequestManifest)
            self.assertEqual(loaded.training_request_id, manifest.training_request_id)

    def test_sft_and_preference_adapters_and_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri, _, snapshot_id, _ = self._seed_store(tempdir)
            adapted_out = Path(tempdir) / "adapted.sft.jsonl"
            summary = export_sft_snapshot_for_logits(
                store_uri=store_uri,
                dataset_snapshot_id=snapshot_id,
                out=adapted_out,
            )
            self.assertEqual(summary["record_count"], 1)
            row = json.loads(adapted_out.read_text(encoding="utf-8").strip())
            self.assertIn("messages", row)
            self.assertEqual(row["metadata"]["dataset_snapshot_id"], snapshot_id)

            request = prepare_sft_training_request(
                store_uri=store_uri,
                dataset_snapshot_id=snapshot_id,
                output_dir=Path(tempdir) / "sft-out",
                base_model="meta-llama/Llama-3.2-1B-Instruct",
                manifest_path=Path(tempdir) / "sft.request.json",
            )
            self.assertEqual(request.recipe_family, "sft")
            self.assertTrue(Path(request.input_path or "").exists())
            self.assertEqual(len(SQLiteFactStore(store_uri).list_training_assets(asset_kind="logits_training_request")), 1)

            pref_store_uri, pref_snapshot_id = self._seed_preference_snapshot(tempdir)
            pref_summary = export_preference_snapshot_for_logits(
                store_uri=pref_store_uri,
                dataset_snapshot_id=pref_snapshot_id,
                train_out=Path(tempdir) / "pref.train.jsonl",
                test_out=Path(tempdir) / "pref.test.jsonl",
                test_size=0,
            )
            self.assertEqual(pref_summary["train_record_count"], 1)
            pref_row = json.loads((Path(tempdir) / "pref.train.jsonl").read_text(encoding="utf-8").strip())
            self.assertEqual(pref_row["label"], "A")
            self.assertIn("comparison", pref_row)

            dpo_request = prepare_dpo_training_request(
                store_uri=pref_store_uri,
                dataset_snapshot_id=pref_snapshot_id,
                output_dir=Path(tempdir) / "dpo-out",
                base_model="meta-llama/Llama-3.2-1B-Instruct",
                manifest_path=Path(tempdir) / "dpo.request.json",
            )
            self.assertEqual(dpo_request.recipe_family, "dpo")
            self.assertTrue(Path(dpo_request.input_path or "").exists())
            self.assertEqual(len(SQLiteFactStore(pref_store_uri).list_training_assets(asset_kind="logits_training_request")), 1)

            rl_request = prepare_rl_training_request(
                output_dir=Path(tempdir) / "rl-out",
                base_model="meta-llama/Llama-3.2-1B-Instruct",
                dataset_builder_ref="clawgraph.tests.test_logits_integration:_FakeRLDatasetBuilder",
                dataset_builder_kwargs={"batch_size": 2},
                slice_id="slice.capture",
                manifest_path=Path(tempdir) / "rl.request.json",
            )
            self.assertEqual(rl_request.recipe_family, "rl")
            self.assertEqual(
                rl_request.runtime_config["dataset_builder_ref"],
                "clawgraph.tests.test_logits_integration:_FakeRLDatasetBuilder",
            )

    def test_submit_evaluate_and_handoff_bridges(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri, _, snapshot_id, suite_id = self._seed_store(tempdir)
            request = prepare_sft_training_request(
                store_uri=store_uri,
                dataset_snapshot_id=snapshot_id,
                output_dir=Path(tempdir) / "sft-out",
                base_model="meta-llama/Llama-3.2-1B-Instruct",
            )
            candidate = submit_training_request(
                request,
                store_uri=store_uri,
                candidate_path=Path(tempdir) / "candidate.json",
                executor=lambda manifest: {
                    "candidate_model": "small-v1",
                    "checkpoint_path": "logits://checkpoint/small-v1",
                    "sampler_path": "logits://sampler/small-v1",
                    "metadata": {"train_steps": 1},
                },
            )
            self.assertEqual(candidate.sampler_path, "logits://sampler/small-v1")
            store = SQLiteFactStore(store_uri)
            self.assertEqual(len(store.list_training_assets(asset_kind="logits_training_request")), 1)
            self.assertEqual(len(store.list_training_assets(asset_kind="logits_model_candidate")), 1)

            def fake_sample(model_descriptor: dict[str, str], case) -> dict[str, float | str]:
                if model_descriptor["label"] == "candidate":
                    return {"text": case.reference_text, "latency_ms": 120.0}
                return {"text": "wrong answer", "latency_ms": 180.0}

            eval_manifest, scorecard, promotion = evaluate_candidate_on_suite(
                store_uri=store_uri,
                eval_suite_id=suite_id,
                candidate_manifest=candidate,
                baseline_model="large-v1",
                sample_fn=fake_sample,
                record_promotion=True,
                output_path=Path(tempdir) / "eval.json",
            )
            self.assertIsInstance(eval_manifest, EvalExecutionManifest)
            self.assertEqual(scorecard.verdict, "pass")
            self.assertIsNotNone(promotion)
            self.assertEqual(promotion.decision, "promote")
            self.assertEqual(len(store.list_training_assets(asset_kind="logits_eval_execution")), 1)

            handoff = create_router_handoff_manifest(
                store_uri=store_uri,
                candidate_manifest=candidate,
                promotion_decision_id=promotion.promotion_decision_id,
                output_path=Path(tempdir) / "handoff.json",
            )
            self.assertIsInstance(handoff, RouterHandoffManifest)
            self.assertEqual(handoff.route_config["fallback"]["target_model"], "large-v1")
            self.assertEqual(len(store.list_training_assets(asset_kind="logits_router_handoff")), 1)

    def test_cli_logit_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store_uri, _, snapshot_id, suite_id = self._seed_store(tempdir)
            request_path = Path(tempdir) / "cli.request.json"
            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "logits",
                    "prepare-sft",
                    "--store",
                    store_uri,
                    "--dataset-snapshot-id",
                    snapshot_id,
                    "--output-dir",
                    str(Path(tempdir) / "cli-sft"),
                    "--base-model",
                    "meta-llama/Llama-3.2-1B-Instruct",
                    "--manifest-out",
                    str(request_path),
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()
            self.assertEqual(return_code, 0)
            request_payload = json.loads(buffer.getvalue())
            self.assertEqual(request_payload["recipe_family"], "sft")

            candidate_path = Path(tempdir) / "cli.candidate.json"
            buffer = StringIO()
            with patch(
                "clawgraph.integrations.logits.training_bridge._builtin_training_executor",
                return_value={
                    "candidate_model": "small-v1",
                    "checkpoint_path": "logits://checkpoint/small-v1",
                    "sampler_path": "logits://sampler/small-v1",
                },
            ), patch(
                "sys.argv",
                [
                    "clawgraph",
                    "logits",
                    "submit",
                    "--store",
                    store_uri,
                    "--manifest",
                    str(request_path),
                    "--candidate-out",
                    str(candidate_path),
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()
            self.assertEqual(return_code, 0)
            candidate_payload = json.loads(buffer.getvalue())
            self.assertEqual(candidate_payload["sampler_path"], "logits://sampler/small-v1")

            def fake_sampler(*, candidate_wins: bool = True):
                def _sample(model_descriptor, case):
                    if model_descriptor["label"] == "candidate":
                        text = case.reference_text if candidate_wins else "wrong"
                        return {"text": text, "latency_ms": 100.0}
                    return {"text": "wrong", "latency_ms": 200.0}

                return _sample

            eval_output = Path(tempdir) / "cli.eval.json"
            buffer = StringIO()
            with patch(
                "clawgraph.integrations.logits.eval_bridge._build_builtin_sampler",
                return_value=fake_sampler(),
            ), patch(
                "sys.argv",
                [
                    "clawgraph",
                    "logits",
                    "evaluate",
                    "--store",
                    store_uri,
                    "--eval-suite-id",
                    suite_id,
                    "--candidate-manifest",
                    str(candidate_path),
                    "--baseline-model",
                    "large-v1",
                    "--record-promotion",
                    "--output",
                    str(eval_output),
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()
            self.assertEqual(return_code, 0)
            eval_payload = json.loads(buffer.getvalue())
            self.assertEqual(eval_payload["scorecard"]["verdict"], "pass")
            promotion_id = eval_payload["promotion"]["promotion_decision_id"]

            handoff_output = Path(tempdir) / "cli.handoff.json"
            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "logits",
                    "handoff",
                    "--store",
                    store_uri,
                    "--candidate-manifest",
                    str(candidate_path),
                    "--promotion-decision-id",
                    promotion_id,
                    "--output",
                    str(handoff_output),
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()
            self.assertEqual(return_code, 0)
            handoff_payload = json.loads(buffer.getvalue())
            self.assertEqual(handoff_payload["decision"], "promote")

            buffer = StringIO()
            with patch(
                "sys.argv",
                ["clawgraph", "logits", "doctor", "--json"],
            ), redirect_stdout(buffer):
                return_code = main()
            self.assertEqual(return_code, 0)
            doctor_payload = json.loads(buffer.getvalue())
            self.assertIn("modules", doctor_payload)
            self.assertTrue(any(item["module"] == "logits" for item in doctor_payload["modules"]))

            manifest_dir = Path(tempdir) / "registry"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            save_manifest(load_manifest(request_path), manifest_dir / "request.json")
            save_manifest(load_manifest(candidate_path), manifest_dir / "candidate.json")
            save_manifest(load_manifest(eval_output), manifest_dir / "execution.json")
            save_manifest(load_manifest(handoff_output), manifest_dir / "handoff.json")

            registry = build_training_registry(manifest_dir=None, store_uri=store_uri)
            self.assertEqual(registry["summary"]["requestCount"], 1)
            self.assertEqual(registry["training_requests"][0]["candidateCount"], 1)
            self.assertEqual(registry["model_candidates"][0]["evalExecutionIds"], [eval_payload["eval_execution"]["eval_execution_id"]])

            buffer = StringIO()
            with patch(
                "sys.argv",
                [
                    "clawgraph",
                    "logits",
                    "registry",
                    "--manifest-dir",
                    str(manifest_dir),
                    "--store",
                    store_uri,
                    "--json",
                ],
            ), redirect_stdout(buffer):
                return_code = main()
            self.assertEqual(return_code, 0)
            registry_payload = json.loads(buffer.getvalue())
            self.assertEqual(registry_payload["summary"]["handoffCount"], 1)


class _FakeRLDatasetBuilder:
    def __init__(self, batch_size: int = 1, **kwargs) -> None:
        self.batch_size = batch_size
        self.kwargs = kwargs
