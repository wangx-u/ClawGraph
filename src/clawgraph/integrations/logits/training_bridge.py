"""Planning and execution bridges from ClawGraph dataset snapshots to Logits training."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any, Callable

from clawgraph.integrations.logits._compat import import_logits_stack, load_dotted_object
from clawgraph.integrations.logits.manifests import (
    ModelCandidateManifest,
    TrainingRequestManifest,
    save_manifest,
)
from clawgraph.integrations.logits.preference_adapter import (
    export_preference_snapshot_for_logits,
)
from clawgraph.integrations.logits.sft_adapter import (
    export_sft_snapshot_for_logits,
    load_dataset_snapshot,
)
from clawgraph.store import SQLiteFactStore


def _default_manifest_path(
    *,
    output_dir: Path,
    request_id: str,
    recipe_family: str,
) -> Path:
    return output_dir / f"{request_id}.{recipe_family}.request.json"


def _default_candidate_path(
    *,
    output_dir: Path,
    candidate_id: str,
) -> Path:
    return output_dir / f"{candidate_id}.candidate.json"


def _default_log_path(
    *,
    output_dir: Path,
    dataset_snapshot_id: str | None,
    recipe_family: str,
) -> str:
    suffix = dataset_snapshot_id or recipe_family
    return str(output_dir / "runs" / f"{suffix}.{recipe_family}")


def _copy_dict(value: dict[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _resolve_snapshot_metadata(store: SQLiteFactStore, dataset_snapshot_id: str) -> dict[str, Any]:
    snapshot = load_dataset_snapshot(store=store, dataset_snapshot_id=dataset_snapshot_id)
    return {
        "cohort_id": snapshot.cohort_id,
        "record_count": snapshot.record_count,
        "sample_unit": snapshot.sample_unit,
        "manifest": snapshot.manifest,
    }


def prepare_sft_training_request(
    *,
    store_uri: str,
    dataset_snapshot_id: str,
    output_dir: Path,
    base_model: str,
    renderer_name: str | None = None,
    log_path: str | None = None,
    base_url: str | None = None,
    api_key_env: str = "LOGITS_API_KEY",
    load_checkpoint_path: str | None = None,
    learning_rate: float = 2e-4,
    lr_schedule: str = "linear",
    num_epochs: int = 1,
    lora_rank: int = 32,
    batch_size: int = 128,
    max_length: int = 32768,
    test_size: int = 0,
    eval_every: int = 10,
    save_every: int = 20,
    ttl_seconds: int | None = 604800,
    max_steps: int | None = None,
    wandb_project: str | None = None,
    wandb_name: str | None = None,
    metadata: dict[str, Any] | None = None,
    manifest_path: Path | None = None,
) -> TrainingRequestManifest:
    """Prepare one SFT training request plus the adapted conversation dataset."""

    store = SQLiteFactStore(store_uri)
    snapshot = load_dataset_snapshot(store=store, dataset_snapshot_id=dataset_snapshot_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_out = output_dir / f"{dataset_snapshot_id}.sft.conversations.jsonl"
    export_sft_snapshot_for_logits(
        store=store,
        dataset_snapshot_id=dataset_snapshot_id,
        out=dataset_out,
    )
    request = TrainingRequestManifest(
        recipe_family="sft",
        recipe_name="supervised.chat_sl",
        base_model=base_model,
        renderer_name=renderer_name,
        dataset_snapshot_id=dataset_snapshot_id,
        dataset_builder=snapshot.builder,
        input_path=str(dataset_out),
        load_checkpoint_path=load_checkpoint_path,
        log_path=log_path or _default_log_path(
            output_dir=output_dir,
            dataset_snapshot_id=dataset_snapshot_id,
            recipe_family="sft",
        ),
        base_url=base_url,
        api_key_env=api_key_env,
        training_config={
            "learning_rate": learning_rate,
            "lr_schedule": lr_schedule,
            "num_epochs": num_epochs,
            "lora_rank": lora_rank,
            "batch_size": batch_size,
            "max_length": max_length,
            "test_size": test_size,
            "eval_every": eval_every,
            "save_every": save_every,
            "ttl_seconds": ttl_seconds,
            "max_steps": max_steps,
            "wandb_project": wandb_project,
            "wandb_name": wandb_name,
        },
        metadata={
            "snapshot": _resolve_snapshot_metadata(store, dataset_snapshot_id),
            **_copy_dict(metadata),
        },
    )
    if manifest_path is not None:
        save_manifest(request, manifest_path)
    else:
        save_manifest(
            request,
            _default_manifest_path(
                output_dir=output_dir,
                request_id=request.training_request_id,
                recipe_family=request.recipe_family,
            ),
        )
    return request


def prepare_dpo_training_request(
    *,
    store_uri: str,
    dataset_snapshot_id: str,
    output_dir: Path,
    base_model: str,
    renderer_name: str | None = None,
    log_path: str | None = None,
    base_url: str | None = None,
    api_key_env: str = "LOGITS_API_KEY",
    load_checkpoint_path: str | None = None,
    learning_rate: float = 1e-5,
    lr_schedule: str = "linear",
    num_epochs: int = 1,
    dpo_beta: float = 0.1,
    lora_rank: int = 32,
    batch_size: int = 256,
    max_length: int = 8192,
    test_size: int = 0,
    eval_every: int = 10,
    save_every: int = 20,
    ttl_seconds: int | None = 604800,
    max_steps: int | None = None,
    wandb_project: str | None = None,
    wandb_name: str | None = None,
    metadata: dict[str, Any] | None = None,
    manifest_path: Path | None = None,
) -> TrainingRequestManifest:
    """Prepare one DPO training request plus the adapted comparison datasets."""

    store = SQLiteFactStore(store_uri)
    snapshot = load_dataset_snapshot(store=store, dataset_snapshot_id=dataset_snapshot_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    train_out = output_dir / f"{dataset_snapshot_id}.dpo.train.jsonl"
    test_out = output_dir / f"{dataset_snapshot_id}.dpo.test.jsonl"
    export_preference_snapshot_for_logits(
        store=store,
        dataset_snapshot_id=dataset_snapshot_id,
        train_out=train_out,
        test_out=test_out,
        test_size=test_size,
    )
    request = TrainingRequestManifest(
        recipe_family="dpo",
        recipe_name="preference.dpo",
        base_model=base_model,
        renderer_name=renderer_name,
        dataset_snapshot_id=dataset_snapshot_id,
        dataset_builder=snapshot.builder,
        input_path=str(train_out),
        test_input_path=str(test_out) if test_size > 0 else None,
        load_checkpoint_path=load_checkpoint_path,
        log_path=log_path or _default_log_path(
            output_dir=output_dir,
            dataset_snapshot_id=dataset_snapshot_id,
            recipe_family="dpo",
        ),
        base_url=base_url,
        api_key_env=api_key_env,
        training_config={
            "learning_rate": learning_rate,
            "lr_schedule": lr_schedule,
            "num_epochs": num_epochs,
            "dpo_beta": dpo_beta,
            "lora_rank": lora_rank,
            "batch_size": batch_size,
            "max_length": max_length,
            "test_size": test_size,
            "eval_every": eval_every,
            "save_every": save_every,
            "ttl_seconds": ttl_seconds,
            "max_steps": max_steps,
            "wandb_project": wandb_project,
            "wandb_name": wandb_name,
        },
        metadata={
            "snapshot": _resolve_snapshot_metadata(store, dataset_snapshot_id),
            **_copy_dict(metadata),
        },
    )
    if manifest_path is not None:
        save_manifest(request, manifest_path)
    else:
        save_manifest(
            request,
            _default_manifest_path(
                output_dir=output_dir,
                request_id=request.training_request_id,
                recipe_family=request.recipe_family,
            ),
        )
    return request


def prepare_rl_training_request(
    *,
    output_dir: Path,
    base_model: str,
    dataset_builder_ref: str,
    dataset_builder_kwargs: dict[str, Any] | None = None,
    renderer_name: str | None = None,
    log_path: str | None = None,
    base_url: str | None = None,
    api_key_env: str = "LOGITS_API_KEY",
    load_checkpoint_path: str | None = None,
    slice_id: str | None = None,
    eval_suite_id: str | None = None,
    learning_rate: float = 4e-5,
    max_tokens: int = 256,
    lora_rank: int = 32,
    eval_every: int = 20,
    save_every: int = 20,
    max_steps: int | None = None,
    metadata: dict[str, Any] | None = None,
    manifest_path: Path | None = None,
) -> TrainingRequestManifest:
    """Prepare one generic environment-driven RL training request."""

    output_dir.mkdir(parents=True, exist_ok=True)
    request = TrainingRequestManifest(
        recipe_family="rl",
        recipe_name="rl.generic_env",
        base_model=base_model,
        renderer_name=renderer_name,
        eval_suite_id=eval_suite_id,
        load_checkpoint_path=load_checkpoint_path,
        log_path=log_path or _default_log_path(
            output_dir=output_dir,
            dataset_snapshot_id=slice_id,
            recipe_family="rl",
        ),
        base_url=base_url,
        api_key_env=api_key_env,
        training_config={
            "learning_rate": learning_rate,
            "max_tokens": max_tokens,
            "lora_rank": lora_rank,
            "eval_every": eval_every,
            "save_every": save_every,
            "max_steps": max_steps,
        },
        runtime_config={
            "dataset_builder_ref": dataset_builder_ref,
            "dataset_builder_kwargs": _copy_dict(dataset_builder_kwargs),
        },
        metadata={
            "slice_id": slice_id,
            **_copy_dict(metadata),
        },
    )
    if manifest_path is not None:
        save_manifest(request, manifest_path)
    else:
        save_manifest(
            request,
            _default_manifest_path(
                output_dir=output_dir,
                request_id=request.training_request_id,
                recipe_family=request.recipe_family,
            ),
        )
    return request


def submit_training_request(
    manifest: TrainingRequestManifest,
    *,
    candidate_path: Path | None = None,
    executor: Callable[[TrainingRequestManifest], Any] | None = None,
) -> ModelCandidateManifest:
    """Submit one training request via the builtin Logits bridge or a custom executor."""

    resolved_executor = executor
    executor_ref = manifest.runtime_config.get("executor_ref")
    if resolved_executor is None and isinstance(executor_ref, str) and executor_ref:
        loaded = load_dotted_object(executor_ref)
        if not callable(loaded):
            raise ValueError(f"executor_ref is not callable: {executor_ref}")
        resolved_executor = loaded
    if resolved_executor is None:
        resolved_executor = _builtin_training_executor
    result = resolved_executor(manifest)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    if isinstance(result, ModelCandidateManifest):
        candidate = result
    elif isinstance(result, dict):
        candidate = ModelCandidateManifest(
            training_request_id=manifest.training_request_id,
            recipe_family=manifest.recipe_family,
            training_recipe=manifest.recipe_name,
            base_model=manifest.base_model,
            renderer_name=manifest.renderer_name,
            dataset_snapshot_id=manifest.dataset_snapshot_id,
            dataset_builder=manifest.dataset_builder,
            candidate_model=result.get("candidate_model")
            or result.get("sampler_path")
            or result.get("checkpoint_path"),
            checkpoint_path=result.get("checkpoint_path"),
            sampler_path=result.get("sampler_path"),
            published_model_path=result.get("published_model_path"),
            log_path=result.get("log_path", manifest.log_path),
            metadata={
                "training_request": manifest.to_dict(),
                **_copy_dict(result.get("metadata")),
            },
        )
    else:
        raise ValueError("training executor must return a dict or ModelCandidateManifest")

    destination = candidate_path
    if destination is None:
        base_dir = Path(manifest.log_path).parent.parent if Path(manifest.log_path).parent.name == "runs" else Path(manifest.log_path).parent
        destination = _default_candidate_path(output_dir=base_dir, candidate_id=candidate.candidate_model_id)
    save_manifest(candidate, destination)
    return candidate


def _builtin_training_executor(manifest: TrainingRequestManifest) -> dict[str, Any]:
    if manifest.recipe_family == "sft":
        return _run_builtin_sft_training(manifest)
    if manifest.recipe_family == "dpo":
        return _run_builtin_dpo_training(manifest)
    if manifest.recipe_family == "rl":
        return _run_builtin_rl_training(manifest)
    raise ValueError(f"unsupported training recipe family: {manifest.recipe_family}")


def _resolve_renderer_name(
    *,
    model_name: str,
    explicit_renderer_name: str | None,
    load_checkpoint_path: str | None,
    base_url: str | None,
) -> str:
    import_logits_stack()
    from logits_cookbook import checkpoint_utils

    return checkpoint_utils.resolve_renderer_name_from_checkpoint_or_default(
        model_name=model_name,
        explicit_renderer_name=explicit_renderer_name,
        load_checkpoint_path=load_checkpoint_path,
        base_url=base_url,
    )


def _run_builtin_sft_training(manifest: TrainingRequestManifest) -> dict[str, Any]:
    import_logits_stack()
    from logits_cookbook import checkpoint_utils
    from logits_cookbook.supervised import train
    from logits_cookbook.supervised.data import FromConversationFileBuilder
    from logits_cookbook.supervised.types import ChatDatasetBuilderCommonConfig

    if not manifest.input_path:
        raise ValueError("sft training request requires input_path")

    renderer_name = _resolve_renderer_name(
        model_name=manifest.base_model,
        explicit_renderer_name=manifest.renderer_name,
        load_checkpoint_path=manifest.load_checkpoint_path,
        base_url=manifest.base_url,
    )
    common_config = ChatDatasetBuilderCommonConfig(
        model_name_for_tokenizer=manifest.base_model,
        renderer_name=renderer_name,
        max_length=int(manifest.training_config.get("max_length", 32768)),
        batch_size=int(manifest.training_config.get("batch_size", 128)),
        train_on_what=manifest.training_config.get("train_on_what"),
    )
    dataset_builder = FromConversationFileBuilder(
        common_config=common_config,
        file_path=manifest.input_path,
        test_size=int(manifest.training_config.get("test_size", 0)),
    )
    config = train.Config(
        log_path=manifest.log_path,
        model_name=manifest.base_model,
        load_checkpoint_path=manifest.load_checkpoint_path,
        renderer_name=renderer_name,
        dataset_builder=dataset_builder,
        learning_rate=float(manifest.training_config.get("learning_rate", 2e-4)),
        lr_schedule=str(manifest.training_config.get("lr_schedule", "linear")),
        num_epochs=int(manifest.training_config.get("num_epochs", 1)),
        lora_rank=int(manifest.training_config.get("lora_rank", 32)),
        base_url=manifest.base_url,
        eval_every=int(manifest.training_config.get("eval_every", 10)),
        save_every=int(manifest.training_config.get("save_every", 20)),
        ttl_seconds=manifest.training_config.get("ttl_seconds", 604800),
        max_steps=manifest.training_config.get("max_steps"),
        wandb_project=manifest.training_config.get("wandb_project"),
        wandb_name=manifest.training_config.get("wandb_name"),
    )
    asyncio.run(train.main(config))
    checkpoint = checkpoint_utils.get_last_checkpoint(manifest.log_path, required_key="sampler_path")
    if checkpoint is None:
        checkpoint = checkpoint_utils.get_last_checkpoint(manifest.log_path, required_key="state_path")
    if checkpoint is None:
        raise ValueError(f"no checkpoints produced in {manifest.log_path}")
    return {
        "candidate_model": checkpoint.sampler_path or checkpoint.state_path,
        "checkpoint_path": checkpoint.state_path,
        "sampler_path": checkpoint.sampler_path,
        "log_path": manifest.log_path,
        "metadata": {
            "checkpoint_name": checkpoint.name,
            "renderer_name": renderer_name,
        },
    }


def _run_builtin_dpo_training(manifest: TrainingRequestManifest) -> dict[str, Any]:
    import_logits_stack()
    from logits_cookbook import checkpoint_utils
    from logits_cookbook.preference.dpo_datasets import DPODatasetBuilderFromComparisons
    from logits_cookbook.preference.preference_datasets import ComparisonBuilderFromJsonl
    from logits_cookbook.preference import train_dpo
    from logits_cookbook.supervised.types import ChatDatasetBuilderCommonConfig

    if not manifest.input_path:
        raise ValueError("dpo training request requires input_path")

    renderer_name = _resolve_renderer_name(
        model_name=manifest.base_model,
        explicit_renderer_name=manifest.renderer_name,
        load_checkpoint_path=manifest.load_checkpoint_path,
        base_url=manifest.base_url,
    )
    common_config = ChatDatasetBuilderCommonConfig(
        model_name_for_tokenizer=manifest.base_model,
        renderer_name=renderer_name,
        max_length=manifest.training_config.get("max_length", 8192),
        batch_size=int(manifest.training_config.get("batch_size", 256)),
    )
    comparison_builder = ComparisonBuilderFromJsonl(
        train_path=manifest.input_path,
        test_path=manifest.test_input_path,
    )
    dataset_builder = DPODatasetBuilderFromComparisons(
        common_config=common_config,
        comparison_builder=comparison_builder,
    )
    config = train_dpo.Config(
        log_path=manifest.log_path,
        model_name=manifest.base_model,
        dataset_builder=dataset_builder,
        load_checkpoint_path=manifest.load_checkpoint_path,
        renderer_name=renderer_name,
        learning_rate=float(manifest.training_config.get("learning_rate", 1e-5)),
        lr_schedule=str(manifest.training_config.get("lr_schedule", "linear")),
        num_epochs=int(manifest.training_config.get("num_epochs", 1)),
        dpo_beta=float(manifest.training_config.get("dpo_beta", 0.1)),
        lora_rank=int(manifest.training_config.get("lora_rank", 32)),
        base_url=manifest.base_url,
        eval_every=int(manifest.training_config.get("eval_every", 10)),
        save_every=int(manifest.training_config.get("save_every", 20)),
        ttl_seconds=manifest.training_config.get("ttl_seconds", 604800),
        max_steps=manifest.training_config.get("max_steps"),
        wandb_project=manifest.training_config.get("wandb_project"),
        wandb_name=manifest.training_config.get("wandb_name"),
    )
    train_dpo.main(config)
    checkpoint = checkpoint_utils.get_last_checkpoint(manifest.log_path, required_key="sampler_path")
    if checkpoint is None:
        checkpoint = checkpoint_utils.get_last_checkpoint(manifest.log_path, required_key="state_path")
    if checkpoint is None:
        raise ValueError(f"no checkpoints produced in {manifest.log_path}")
    return {
        "candidate_model": checkpoint.sampler_path or checkpoint.state_path,
        "checkpoint_path": checkpoint.state_path,
        "sampler_path": checkpoint.sampler_path,
        "log_path": manifest.log_path,
        "metadata": {
            "checkpoint_name": checkpoint.name,
            "renderer_name": renderer_name,
        },
    }


def _instantiate_dataset_builder(ref: str, kwargs: dict[str, Any]) -> Any:
    loaded = load_dotted_object(ref)
    if inspect.isclass(loaded):
        return loaded(**kwargs)
    if callable(loaded):
        candidate = loaded(**kwargs)
        return candidate
    raise ValueError(f"dataset builder ref is not constructible: {ref}")


def _run_builtin_rl_training(manifest: TrainingRequestManifest) -> dict[str, Any]:
    import_logits_stack()
    from logits_cookbook import checkpoint_utils
    from logits_cookbook.rl import train as rl_train

    dataset_builder_ref = manifest.runtime_config.get("dataset_builder_ref")
    if not isinstance(dataset_builder_ref, str) or not dataset_builder_ref:
        raise ValueError("rl training request requires runtime_config.dataset_builder_ref")

    dataset_builder_kwargs = _copy_dict(manifest.runtime_config.get("dataset_builder_kwargs"))
    renderer_name = manifest.renderer_name or dataset_builder_kwargs.get("renderer_name")
    if renderer_name is not None:
        dataset_builder_kwargs.setdefault("renderer_name", renderer_name)
    dataset_builder_kwargs.setdefault("model_name_for_tokenizer", manifest.base_model)
    dataset_builder = _instantiate_dataset_builder(dataset_builder_ref, dataset_builder_kwargs)
    config = rl_train.Config(
        learning_rate=float(manifest.training_config.get("learning_rate", 4e-5)),
        dataset_builder=dataset_builder,
        model_name=manifest.base_model,
        max_tokens=int(manifest.training_config.get("max_tokens", 256)),
        log_path=manifest.log_path,
        eval_every=int(manifest.training_config.get("eval_every", 20)),
        save_every=int(manifest.training_config.get("save_every", 20)),
        load_checkpoint_path=manifest.load_checkpoint_path,
        renderer_name=renderer_name,
        lora_rank=int(manifest.training_config.get("lora_rank", 32)),
        base_url=manifest.base_url,
        max_steps=manifest.training_config.get("max_steps"),
    )
    asyncio.run(rl_train.main(config))
    checkpoint = checkpoint_utils.get_last_checkpoint(manifest.log_path, required_key="sampler_path")
    if checkpoint is None:
        checkpoint = checkpoint_utils.get_last_checkpoint(manifest.log_path, required_key="state_path")
    if checkpoint is None:
        raise ValueError(f"no checkpoints produced in {manifest.log_path}")
    return {
        "candidate_model": checkpoint.sampler_path or checkpoint.state_path,
        "checkpoint_path": checkpoint.state_path,
        "sampler_path": checkpoint.sampler_path,
        "log_path": manifest.log_path,
        "metadata": {
            "checkpoint_name": checkpoint.name,
            "renderer_name": renderer_name,
            "dataset_builder_ref": dataset_builder_ref,
        },
    }

